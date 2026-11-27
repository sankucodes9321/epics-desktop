"""Optional native widget smoke test on a private Unix-only GTK display.

Run /usr/bin/python3 tests/gtk_smoke.py in the checkout on Fedora.
"""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]


def exercise():
    import gi
    gi.require_version("Gtk", "4.0")
    from gi.repository import Gtk, GLib
    sys.path.insert(0, str(ROOT))
    import teacher_app
    import student_verifier

    results = []
    summary_file = str(Path.home() / "demo-public.json")
    receipt_file = str(Path.home() / "demo-receipt.json")
    original = Gtk.Application.run
    def run_teacher(app, arguments):
        import signal
        import traceback
        def steps(w):
            def click(label):
                button = w.actions[label]
                assert button.get_sensitive(), f"Inactive button: {label}"
                button.emit("clicked")

            def confirm():
                dialog = next(window for window in Gtk.Window.get_toplevels()
                              if isinstance(window, Gtk.MessageDialog) and window.get_transient_for() == w)
                dialog.emit("response", Gtk.ResponseType.OK)

            def page(name):
                w.stack.set_visible_child_name(name)

            assert w.stack.get_visible_child_name() == "Enrollment"
            assert not w.actions["Mark once"].get_sensitive()
            w.fields["name"].set_text("Synthetic student")
            click("Enroll sample")
            yield
            click("Verify student")
            yield
            assert "Identity verified" in w.status.get_text()
            page("Live class")
            w.fields["label"].set_text("Widget smoke")
            click("Open class")
            yield
            assert w.sid()
            click("Mark once")
            yield
            assert w.status.get_text() == "Marked · demo-student"
            click("Start scanning")
            yield
            assert w.status.get_text() == "Already marked · demo-student"
            w.cancel.emit("clicked")
            assert not w.loop and w.scan_timer is None
            page("Register")
            click("View register")
            yield
            assert len(w.register["marks"]) == 1
            w.search.set_text("missing")
            w.render_register()
            assert w.roster.get_first_child().get_child().get_text() == "No matching students"
            click("Finalize class")
            confirm()
            yield
            assert w.get("revision") == "1" and not w.actions["Mark once"].get_sensitive()
            w.appeal.set_expanded(True)
            w.fields["correct_uid"].set_text("demo-student")
            w.fields["reason"].set_text("Reviewed attendance")
            w.decision.set_active(2)
            click("Issue signed revision")
            confirm()
            yield
            assert w.get("revision") == "2" and w.register["corrections"][-1]["upheld"]
            page("Publication")
            click("Show public QR")
            yield
            qr = next(win for win in Gtk.Window.get_toplevels() if win.get_title() == "Show public QR")
            assert isinstance(qr.get_child(), Gtk.DrawingArea)
            qr.close()
            w.session_op("publish", {"path": summary_file})
            yield
            w.session_op("receipt", {"uid": "demo-student", "path": receipt_file})
            yield
            assert Path(summary_file).is_file() and Path(receipt_file).is_file()
            page("Evaluation")
            w.fields["expected"].set_text("demo-student")
            click("Run trial")
            yield
            assert "Correct" in w.status.get_text()
            page("Retention")
            assert not w.get("cutoff")
            w.fields["cutoff"].set_text("2099-01-01")
            click("Preview records")
            yield
            assert w.actions["Delete previewed records"].get_sensitive()
            w.fields["cutoff"].set_text("2098-01-01")
            assert not w.actions["Delete previewed records"].get_sensitive()
            click("Preview records")
            yield
            click("Delete previewed records")
            confirm()
            yield
            assert not w.sid() and not w.actions["Export public register"].get_sensitive()
            w.worker.signal(signal.SIGKILL)
            click("Refresh sessions")
            yield
            assert w.failed and w.restart.get_visible()
            w.restart.emit("clicked")
            confirm()
            yield
            assert not w.failed and not w.sid() and w.actions["Refresh sessions"].get_sensitive()
            results.append("teacher")

        workflow = None
        def drive():
            nonlocal workflow
            w = app.get_active_window()
            if not w or w.busy:
                return True
            try:
                if workflow is None:
                    workflow = steps(w)
                next(workflow)
                return True
            except StopIteration:
                w.close()
            except BaseException:
                traceback.print_exc()
                results.append("failed")
                w.close()
            return False
        GLib.timeout_add(100, drive)
        return original(app, arguments)
    Gtk.Application.run = run_teacher
    teacher_app.launch(True, False)
    assert results and "failed" not in results

    def run_student(app, arguments):
        def finish():
            win = app.get_active_window()
            if win is None:
                return True
            panel = win.get_child()
            widgets = [widget for row in panel for widget in ([row, *list(row)] if isinstance(row, Gtk.Box) else [row])]
            entries = [widget for widget in widgets if isinstance(widget, Gtk.Entry)]
            entries[0].set_text(summary_file)
            entries[1].set_text(receipt_file)
            next(widget for widget in widgets if isinstance(widget, Gtk.CheckButton)).set_active(True)
            button = next(widget for widget in widgets if isinstance(widget, Gtk.Button)
                          and widget.get_label() == "Verify inclusion")
            button.emit("clicked")
            status = panel.get_last_child()
            if "Included in Widget smoke" in status.get_text() and "revision 2" in status.get_text():
                entries[1].set_text("")
                if not status.get_text() and not button.get_sensitive():
                    results.append(win.get_title())
            win.close()
            return False
        GLib.timeout_add(100, finish)
        return original(app, arguments)
    Gtk.Application.run = run_student
    student_verifier.gtk_gui()
    assert results[-1] == "Attendance receipt verifier"
    print("PASS: native teacher and student windows, enrollment, repeated scans, cancellation, search, revision, export, trial, retention, worker restart and independent verification")


def main():
    with tempfile.TemporaryDirectory() as directory:
        env = {"PATH": os.defpath, "HOME": directory, "XDG_RUNTIME_DIR": directory,
               "XDG_CACHE_HOME": directory, "GDK_BACKEND": "broadway", "BROADWAY_DISPLAY": ":37",
               "GTK_A11Y": "none", "GSK_RENDERER": "cairo", "GSETTINGS_BACKEND": "memory",
               "DBUS_SESSION_BUS_ADDRESS": "unix:path=" + directory + "/unused"}
        proc = subprocess.Popen(["/usr/bin/gtk4-broadwayd", "-u", directory + "/browser.sock", ":37"],
                                env=env, stdout=subprocess.DEVNULL)
        try:
            for _ in range(100):
                if proc.poll() is not None:
                    sys.exit("Unable to start private GTK display.")
                if (Path(directory)/"browser.sock").is_socket():
                    break
                time.sleep(.02)
            subprocess.run([sys.executable, __file__, "--widgets"], env=env, timeout=35, check=True)
        finally:
            proc.terminate()
            proc.wait(timeout=5)


if __name__ == "__main__":
    if sys.argv[1:] == ["--widgets"]:
        exercise()
    else:
        main()
