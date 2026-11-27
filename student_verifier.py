"""Portable attendance receipt verification. Requires only Python and cryptography."""
import argparse
import base64
import hashlib
import json
import os
import re
import stat
import sys

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

SCHEME = "zkauth-session-v1"
DEMO_PUBLIC = "O2onvM62pC1io6jQKm8Nc2UyFXcd4kOmOsBIoYtZ2ik="


class VerificationError(ValueError):
    """A verification diagnostic that is safe to display to the receipt holder."""


def canonical(obj):
    return json.dumps(obj, ensure_ascii=True, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def digest(value):
    return hashlib.sha256(value).hexdigest()


def hex_bytes(value, size):
    if not isinstance(value, str) or not re.fullmatch("[0-9a-f]{%d}" % (2 * size), value):
        raise VerificationError("Invalid proof encoding.")
    return bytes.fromhex(value)


def commitment(session, token):
    return digest(b"zkauth/receipt/v1\0" + hex_bytes(session, 16) + hex_bytes(token, 32))


def parent(left, right):
    return digest(b"\x01" + hex_bytes(left, 32) + hex_bytes(right, 32))


def tree(leaves):
    level = sorted(leaves)
    if len(set(level)) != len(level):
        raise VerificationError("Duplicate commitment.")
    for leaf in level:
        hex_bytes(leaf, 32)
    levels = [level or [digest(b"zkauth/empty/v1")]]
    while len(levels[-1]) > 1:
        level = levels[-1]
        levels.append([parent(level[i], level[min(i + 1, len(level) - 1)]) for i in range(0, len(level), 2)])
    return levels


def make_path(levels, index):
    result = []
    for level in levels[:-1]:
        sibling = index ^ 1
        result.append(level[sibling] if sibling < len(level) else level[index])
        index //= 2
    return result


def inspect_document(document, public_b64, demo=False):
    bulletin = document if "document" in document else None
    if bulletin is not None:
        document = bulletin["document"]
    summary = document["summary"]
    pinned = base64.b64decode(public_b64, validate=True)
    if (pinned == base64.b64decode(DEMO_PUBLIC)) != demo:
        raise VerificationError("Public key belongs to the wrong trust domain.")
    Ed25519PublicKey.from_public_bytes(pinned).verify(
        hex_bytes(document["signature"], 64), canonical(summary))
    if summary["scheme"] != SCHEME or summary["mode"] != ("demo" if demo else "live"):
        raise VerificationError("Unexpected signing domain.")
    if (type(summary["revision"]) is not int or summary["revision"] < 1
            or not isinstance(summary["label"], str) or not summary["label"].isprintable()):
        raise VerificationError("Invalid session metadata.")
    hex_bytes(summary["session"], 16)
    hex_bytes(summary["root"], 32)
    if type(summary["count"]) is not int or not 0 <= summary["count"] <= 1000:
        raise VerificationError("Invalid session size.")
    levels = None
    if bulletin is not None:
        leaves = bulletin["commitments"]
        if not isinstance(leaves, list) or len(leaves) != summary["count"]:
            raise VerificationError("Register count mismatch.")
        levels = tree(leaves)
        if levels[-1][0] != summary["root"]:
            raise VerificationError("Register differs from signed root.")
    return summary, levels


def verify(document, receipt, public_b64, demo=False):
    summary, levels = inspect_document(document, public_b64, demo)
    if receipt["session"] != summary["session"]:
        raise VerificationError("The receipt belongs to a different class.")
    if "revision" not in receipt:
        if levels is None:
            raise VerificationError("This receipt was issued before closure. Select the exported public register.")
        if "index" in receipt or "path" in receipt:
            raise VerificationError("Incomplete receipt proof.")
        leaf = commitment(receipt["session"], receipt["token"])
        try:
            index = levels[0].index(leaf)
        except ValueError:
            raise VerificationError("This receipt is absent from the selected register.") from None
        receipt = dict(receipt, revision=summary["revision"], index=index, path=make_path(levels, index))
    if type(receipt["revision"]) is not int or receipt["revision"] != summary["revision"]:
        raise VerificationError("Session or revision mismatch.")
    index, count = receipt["index"], summary["count"]
    if type(index) is not int or type(count) is not int or not 0 <= index < count:
        raise VerificationError("Invalid leaf position.")
    node = commitment(receipt["session"], receipt["token"])
    siblings = receipt["path"]
    if not isinstance(siblings, list) or len(siblings) != (count - 1).bit_length():
        raise VerificationError("Invalid proof length.")
    for sibling in siblings:
        if (index ^ 1) >= count and sibling != node:
            raise VerificationError("Invalid odd leaf.")
        node = parent(sibling, node) if index % 2 else parent(node, sibling)
        index //= 2
        count = (count + 1) // 2
    if node != summary["root"]:
        raise VerificationError("Receipt differs from signed register.")
    return summary


def read_document(path):
    def open_document(name, flags):
        return os.open(name, flags | getattr(os, "O_NONBLOCK", 0))

    with open(path, "rb", opener=open_document) as handle:
        if not stat.S_ISREG(os.fstat(handle.fileno()).st_mode):
            raise VerificationError("Choose a regular document file.")
        raw = handle.read(262145)
    if len(raw) > 262144:
        raise VerificationError("Document too large.")
    try:
        obj = json.loads(raw)
    except RecursionError:
        raise VerificationError("Invalid document structure.") from None
    if not isinstance(obj, dict):
        raise VerificationError("Expected a document object.")
    return obj


def check(summary_path, receipt_path, pin, demo):
    if not demo and (not pin or pin == DEMO_PUBLIC):
        raise VerificationError("Supply the school's independently obtained public key.")
    return verify(read_document(summary_path), read_document(receipt_path), DEMO_PUBLIC if demo else pin, demo)


def verification_result(summary_path, receipt_path, pin, demo):
    try:
        result = check(summary_path, receipt_path, pin, demo)
        return True, confirmation(result)
    except OSError:
        return False, "Could not read a file. Select readable local copies of the register and receipt."
    except InvalidSignature:
        return False, "The signature does not match. Check the register, verification mode and trusted school key."
    except (KeyError, TypeError, RecursionError, UnicodeError, json.JSONDecodeError):
        return False, "Invalid document. Select the exported register and the student's private receipt."
    except VerificationError as error:
        return False, str(error)
    except ValueError:
        return False, "Invalid document or public key. Check both files and the trusted school key."


def gtk_gui(demo_default=False):
    import gi
    gi.require_version("Gtk", "4.0")
    gi.require_version("Gdk", "4.0")
    from gi.repository import Gdk, Gio, Gtk
    if Gdk.Display.get_default() is None:
        raise RuntimeError("A graphical display is required. Use --summary and --receipt to verify from the terminal.")
    app = Gtk.Application(application_id="in.epics.StudentVerifier", flags=Gio.ApplicationFlags.NON_UNIQUE)

    def activate(instance):
        win = Gtk.ApplicationWindow(application=instance, title="Attendance receipt verifier")
        win.set_default_size(560, 420)
        panel = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        for edge in ("start", "end", "top", "bottom"):
            getattr(panel, "set_margin_" + edge)(22)
        win.set_child(panel)
        panel.append(Gtk.Label(label="Verify attendance", xalign=0, css_classes=["title-1"]))
        fields = []
        for label in ("Signed summary or public register", "Private receipt", "Trusted school public key"):
            caption = Gtk.Label(label=label, xalign=0, css_classes=["heading"])
            panel.append(caption)
            field = Gtk.Entry(hexpand=True)
            field.update_property([Gtk.AccessibleProperty.LABEL], [label])
            caption.set_mnemonic_widget(field)
            row = Gtk.Box(spacing=8)
            row.append(field)
            panel.append(row)
            fields.append(field)
            if len(fields) < 3:
                browse = Gtk.Button(label="Browse")
                browse.update_property([Gtk.AccessibleProperty.LABEL], ["Browse for " + label.lower()])
                def pick(_, target=field):
                    dialog = Gtk.FileChooserNative.new("Open document", win, Gtk.FileChooserAction.OPEN, "Open", "Cancel")
                    def selected(d, response):
                        if response == Gtk.ResponseType.ACCEPT and d.get_file():
                            path = d.get_file().get_path()
                            if path:
                                target.set_text(path)
                        d.destroy()
                    dialog.connect("response", selected)
                    dialog.show()
                browse.connect("clicked", pick)
                row.append(browse)
        fields[2].set_text(os.getenv("ZKAUTH_SCHOOL_PUBLIC_KEY", ""))
        demo = Gtk.CheckButton(label="Verify synthetic demo", active=demo_default)
        panel.append(demo)
        button = Gtk.Button(label="Verify inclusion", halign=Gtk.Align.START, css_classes=["suggested-action"])
        status = Gtk.Label(wrap=True, selectable=True, xalign=0)
        status.update_property([Gtk.AccessibleProperty.LABEL], ["Verification result"])

        def values():
            return [field.get_text().strip() for field in fields]

        def changed(*_):
            summary, receipt, key = values()
            fields[2].set_sensitive(not demo.get_active())
            button.set_sensitive(bool(summary and receipt and (key or demo.get_active())))
            status.set_text("")

        def submit(_):
            ok, result = verification_result(*values(), demo.get_active())
            status.set_css_classes(["success" if ok else "error"])
            status.set_text(result)
        for field in fields:
            field.connect("changed", changed)
        demo.connect("toggled", changed)
        button.connect("clicked", submit)
        panel.append(button)
        panel.append(status)
        changed()
        win.present()
    app.connect("activate", activate)
    return app.run([])


def confirmation(summary):
    return (f"{summary['mode'].upper()}: Included in {summary['label']} "
            f"(session {summary['session']}, revision {summary['revision']}).")


def gui(demo_default=False):
    try:
        import tkinter as tk
    except ImportError:
        return gtk_gui(demo_default)
    from tkinter import filedialog, ttk
    try:
        root = tk.Tk()
    except tk.TclError:
        return gtk_gui(demo_default)
    root.title("Attendance receipt verifier")
    panel = ttk.Frame(root, padding=22)
    panel.pack(fill="both", expand=True)
    panel.columnconfigure(0, weight=1)
    ttk.Label(panel, text="Verify attendance", font="TkHeadingFont").grid(row=0, column=0, sticky="w")
    fields = []
    def browse(field):
        selected = filedialog.askopenfilename(parent=root)
        if selected:
            field.set(selected)
    for index, label in enumerate(("Signed summary or public register", "Private receipt", "Trusted school public key")):
        row = index * 2 + 1
        field = tk.StringVar(value=os.getenv("ZKAUTH_SCHOOL_PUBLIC_KEY", "") if index == 2 else "")
        fields.append(field)
        ttk.Label(panel, text=label).grid(row=row, column=0, sticky="w", pady=(10, 2))
        entry = ttk.Entry(panel, textvariable=field, width=50)
        entry.grid(row=row + 1, column=0, sticky="ew")
        if index < 2:
            ttk.Button(panel, text="Browse", command=lambda f=field: browse(f)).grid(row=row + 1, column=1, padx=(8, 0))
    key_entry = entry
    demo = tk.BooleanVar(value=demo_default)
    ttk.Checkbutton(panel, text="Verify synthetic demo", variable=demo).grid(row=7, column=0, sticky="w", pady=8)
    status = tk.StringVar()
    def values():
        return [field.get().strip() for field in fields]
    def submit():
        _, result = verification_result(*values(), demo.get())
        status.set(result)
    button = ttk.Button(panel, text="Verify inclusion", command=submit)
    button.grid(row=8, column=0, sticky="w")
    ttk.Label(panel, textvariable=status, wraplength=440).grid(row=9, columnspan=2, sticky="w", pady=(8, 0))
    def changed(*_):
        summary, receipt, key = values()
        button.state(["!disabled" if summary and receipt and (key or demo.get()) else "disabled"])
        key_entry.state(["disabled" if demo.get() else "!disabled"])
        status.set("")
    for field in [*fields, demo]:
        field.trace_add("write", changed)
    changed()
    root.mainloop()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--summary")
    parser.add_argument("--receipt")
    parser.add_argument("--demo", action="store_true")
    args = parser.parse_args()
    if args.summary or args.receipt:
        if not (args.summary and args.receipt):
            parser.error("Provide both --summary and --receipt.")
        ok, result = verification_result(args.summary, args.receipt, os.getenv("ZKAUTH_SCHOOL_PUBLIC_KEY"), args.demo)
        if not ok:
            sys.exit("Verification failed. " + result)
        print(result)
    else:
        try:
            gui(args.demo)
        except RuntimeError as error:
            sys.exit(str(error))
        except (ImportError, ValueError):
            sys.exit("Install Python Tk support for the GUI, or use --summary and --receipt.")


if __name__ == "__main__":
    main()
