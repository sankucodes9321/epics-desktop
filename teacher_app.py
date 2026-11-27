"""Fedora GTK 4 teacher desktop. Run with /usr/bin/python3 teacher_app.py."""
import argparse
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import threading

ROOT = Path(__file__).resolve().parent
HI = {
    "Teacher workspace": "शिक्षक कार्यक्षेत्र", "System check": "सिस्टम जाँच",
    "Enrollment": "पंजीकरण", "Live class": "कक्षा उपस्थिति", "Register": "उपस्थिति सूची",
    "Publication": "प्रकाशन", "Evaluation": "मूल्यांकन", "Retention": "डेटा हटाना",
    "Run checks": "जाँच करें", "Student ID": "विद्यार्थी आईडी", "Name": "नाम",
    "Enroll sample": "नमूना दर्ज करें", "Verify student": "पहचान जाँचें",
    "Course, section and lecture": "पाठ्यक्रम, अनुभाग और व्याख्यान", "Open class": "कक्षा बनाएँ",
    "Selected session": "चुनी हुई कक्षा", "Refresh sessions": "कक्षाएँ दिखाएँ",
    "Mark once": "एक बार दर्ज करें", "Start scanning": "स्कैन शुरू करें", "Cancel scan": "स्कैन रोकें",
    "View register": "सूची देखें", "Finalize class": "कक्षा बंद करें",
    "Export private receipt": "निजी रसीद सहेजें", "Export public register": "सार्वजनिक सूची सहेजें",
    "Show public QR": "सार्वजनिक क्यूआर देखें", "Revision reviewed": "समीक्षित संस्करण",
    "Correction": "सुधार", "Appeal or correction reason": "अपील या सुधार का कारण",
    "Issue signed revision": "हस्ताक्षरित संशोधन जारी करें", "Trial type": "परीक्षण प्रकार",
    "Run trial": "परीक्षण करें", "Export aggregate results": "समेकित परिणाम सहेजें",
    "Local cutoff date": "स्थानीय अंतिम तिथि", "Preview records": "रिकॉर्ड देखें",
    "Delete previewed records": "चुने हुए रिकॉर्ड हटाएँ", "Ready": "तैयार",
    "Synthetic demo": "कृत्रिम डेमो", "Live deployment": "वास्तविक प्रणाली",
    "Simulated student ID": "कृत्रिम विद्यार्थी आईडी", "Cancel": "रद्द करें", "Confirm": "पुष्टि करें",
    "School attendance": "विद्यालय उपस्थिति", "Working": "प्रक्रिया जारी है",
    "Save": "सहेजें", "Latest result": "नवीनतम परिणाम", "Select session first": "पहले कक्षा चुनें",

    "No classes yet": "अभी कोई कक्षा नहीं है", "Open": "जारी", "Closed": "बंद",
    "Find by name or student ID": "नाम या विद्यार्थी आईडी खोजें",
    "No attendance recorded": "अभी कोई उपस्थिति नहीं है", "No matching students": "कोई मिलान नहीं मिला",
    "Present": "उपस्थित", "Local time": "स्थानीय समय", "Loading": "लोड हो रहा है",
    "Correction history": "सुधार का इतिहास", "No records before this date": "इस तिथि से पहले कोई रिकॉर्ड नहीं",
    "Restart worker": "वर्कर फिर शुरू करें", "Restart the attendance worker": "उपस्थिति वर्कर फिर शुरू करें",
    "Restarting clears this synthetic class": "फिर शुरू करने पर यह कृत्रिम कक्षा मिट जाएगी",
    "Identity verified": "पहचान सत्यापित", "No identity match": "पहचान मेल नहीं खाती",
    "No enrolled match": "कोई पंजीकृत मिलान नहीं", "Score": "स्कोर",
    "Marked": "उपस्थिति दर्ज", "Already marked": "पहले से दर्ज",
    "Expected student ID": "अपेक्षित विद्यार्थी आईडी", "Correct": "सही",
    "Incorrect": "गलत", "Inconclusive": "अनिर्णायक",
    "View the register to review attendance.": "उपस्थिति देखने के लिए सूची खोलें।",
    "Open a class in Live class to start taking attendance.": "उपस्थिति के लिए कक्षा उपस्थिति में कक्षा बनाएँ।",
    "Records deleted": "रिकॉर्ड हटाए गए", "Revision": "संस्करण",
    "Check the capture setup, storage connection and school signing key.": "कैमरा सेटअप, स्टोरेज कनेक्शन और विद्यालय की हस्ताक्षर कुंजी जाँचें।",
    "Use the same student ID for up to five enrollment samples.": "अधिकतम पाँच पंजीकरण नमूनों के लिए एक ही विद्यार्थी आईडी प्रयोग करें।",
    "Open one session per lecture. Each student counts once per session.": "हर व्याख्यान के लिए एक कक्षा खोलें। हर विद्यार्थी की उपस्थिति एक बार दर्ज होगी।",
    "Review attendance before finalizing. Later corrections issue a new signed revision.": "कक्षा बंद करने से पहले उपस्थिति जाँचें। बाद के सुधार से नया हस्ताक्षरित संस्करण बनेगा।",
    "Give receipts to students privately. Finalize the class to share the public register or QR.": "विद्यार्थियों को रसीदें निजी रूप से दें। सार्वजनिक सूची या क्यूआर साझा करने के लिए कक्षा बंद करें।",
    "Choose a trial and record its outcome. Export the results before closing the workspace.": "परीक्षण चुनें और परिणाम दर्ज करें। कार्यक्षेत्र बंद करने से पहले परिणाम सहेजें।",
    "Preview daily attendance and closed classes older than the cutoff date.": "अंतिम तिथि से पहले की दैनिक उपस्थिति और बंद कक्षाओं के रिकॉर्ड देखें।",
}


class Worker:
    def __init__(self, demo):
        command = [str(ROOT / ".venv/bin/python"), "-m", "scripts.classroom_worker"]
        if demo:
            command.append("--demo")
        self.process = subprocess.Popen(command, cwd=ROOT, start_new_session=True, text=True,
                                        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)

    def call(self, action, args):
        self.process.stdin.write(json.dumps(dict(action=action, args=args)) + "\n")
        self.process.stdin.flush()
        line = self.process.stdout.readline()
        if not line:
            raise EOFError
        return json.loads(line)

    def signal(self, sig):
        try:
            os.killpg(self.process.pid, sig)
        except ProcessLookupError:
            pass

    def close(self):
        self.signal(signal.SIGINT)
        try:
            self.process.wait(timeout=1)
        except subprocess.TimeoutExpired:
            self.signal(signal.SIGKILL)
            self.process.wait()
        self.process.stdin.close()
        self.process.stdout.close()


def launch(demo, hindi):
    import gi
    gi.require_version("Gtk", "4.0")
    from gi.repository import Gtk, Gio, GLib, Gdk, Pango
    if Gdk.Display.get_default() is None:
        sys.exit("Open the teacher app from a Fedora graphical desktop session.")
    tr = lambda s: HI.get(s, s) if hindi else s

    class Window(Gtk.ApplicationWindow):
        def __init__(self, app):
            super().__init__(application=app, title=tr("Teacher workspace"))
            self.set_default_size(980, 720)
            self.worker = None
            self.failed = False
            self.scan_timer = None
            self.preview_cutoff = None
            self.register = None
            self.busy = None
            self.serial = 0
            self.loop = False
            self.closing = False
            self.fields = {}
            self.actions = {}
            self.sessions = []
            self.connect("close-request", self.shutdown)
            outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
            self.set_child(outer)
            bar = Gtk.HeaderBar()
            brand = Gtk.Box(spacing=8)
            brand.append(Gtk.Image.new_from_icon_name("view-list-symbolic"))
            brand.append(Gtk.Label(label=tr("School attendance"), css_classes=["heading"]))
            bar.set_title_widget(brand)
            bar.pack_start(Gtk.Label(label=tr("Synthetic demo" if demo else "Live deployment"),
                                     css_classes=["mode-chip"]))
            self.cancel = Gtk.Button(label=tr("Cancel scan"))
            self.cancel.connect("clicked", self.stop_scan)
            self.cancel.set_sensitive(False)
            bar.pack_end(self.cancel)
            self.restart = Gtk.Button(label=tr("Restart worker"), visible=False)
            self.restart.connect("clicked", lambda *_: self.confirm(
                "Restarting clears this synthetic class" if demo else "Restart the attendance worker",
                self.start_worker))
            bar.pack_end(self.restart)
            self.set_titlebar(bar)
            self.stack = Gtk.Stack()
            body = Gtk.Box(spacing=12)
            outer.append(body)
            body.set_vexpand(True)
            sidebar = Gtk.StackSidebar()
            sidebar.set_stack(self.stack)
            sidebar.set_size_request(165, -1)
            sidebar.add_css_class("navigation-sidebar")
            body.append(sidebar)
            layout = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
            layout.set_hexpand(True)
            layout.add_css_class("workspace")
            body.append(layout)
            session_row = Gtk.Box(spacing=8)
            session_row.add_css_class("session-bar")
            layout.append(session_row)
            session_row.append(Gtk.Label(label=tr("Selected session")))
            self.selector = Gtk.ComboBoxText()
            self.selector.update_property([Gtk.AccessibleProperty.LABEL], [tr("Selected session")])
            self.selector.set_hexpand(True)
            for cell in self.selector.get_cells():
                cell.set_property("ellipsize", Pango.EllipsizeMode.END)
                cell.set_property("max-width-chars", 48)
            session_row.append(self.selector)
            self.button(session_row, "Refresh sessions", self.refresh)
            self.stack.set_vexpand(True)
            layout.append(self.stack)
            footer = Gtk.Box(spacing=10, css_classes=["status-bar"])
            self.spinner = Gtk.Spinner()
            footer.append(self.spinner)
            self.status = Gtk.Label(label=tr("Ready"), xalign=0, wrap=True, selectable=True)
            footer.append(self.status)
            outer.append(footer)
            self.pages()
            if demo:
                self.stack.set_visible_child_name("Enrollment")
            self.start_worker()

        def start_worker(self):
            if self.worker is not None:
                self.worker.close()
            self.worker = None
            self.selector.remove_all()
            self.sessions = []
            self.clear_preview()
            try:
                self.worker = Worker(demo)
            except OSError:
                self.worker_failed("Worker unavailable. Run make setup in the project folder, then restart the worker.")
                return
            self.failed = False
            self.restart.set_visible(False)
            self.refresh()

        def worker_failed(self, message):
            self.failed = True
            self.loop = False
            self.status.set_text(message)
            self.restart.set_visible(True)
            self.enable(False)

        def page(self, name, description):
            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
            for edge in ("top", "bottom", "start", "end"):
                getattr(box, "set_margin_" + edge)(20)
            scroll = Gtk.ScrolledWindow()
            scroll.set_child(box)
            self.stack.add_titled(scroll, name, tr(name))
            box.add_css_class("page-surface")
            box.set_valign(Gtk.Align.START)
            title = Gtk.Label(label=tr(name), xalign=0)
            title.add_css_class("page-title")
            box.append(title)
            box.append(Gtk.Label(label=tr(description), xalign=0, wrap=True, css_classes=["page-description"]))
            return box

        def field(self, box, key, label, default="", placeholder=""):
            entry = Gtk.Entry(text=default, placeholder_text=placeholder)
            caption = Gtk.Label(label=tr(label), xalign=0)
            caption.set_mnemonic_widget(entry)
            entry.update_property([Gtk.AccessibleProperty.LABEL], [tr(label)])
            group = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
            caption.add_css_class("field-caption")
            group.append(caption)
            group.append(entry)
            box.append(group)
            self.fields[key] = entry

        def row(self, box):
            row = Gtk.Box(spacing=8)
            box.append(row)
            return row

        def button(self, box, label, action, style=None):
            b = Gtk.Button(label=tr(label))
            b.set_halign(Gtk.Align.START)
            b.connect("clicked", lambda *_: action())
            box.append(b)
            if style:
                b.add_css_class(style)
            self.actions[label] = b

        def output(self, box):
            view = Gtk.TextView(editable=False, cursor_visible=False, monospace=True)
            view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
            view.set_size_request(-1, 160)
            view.set_left_margin(12)
            view.set_top_margin(10)
            view.set_bottom_margin(10)
            view.add_css_class("report-output")
            box.append(view)
            return lambda value: view.get_buffer().set_text(value if isinstance(value, str)
                                                           else json.dumps(value, ensure_ascii=False, indent=2))

        def pages(self):
            box = self.page("System check", "Check the capture setup, storage connection and school signing key.")
            show = self.output(box)
            self.button(box, "Run checks", lambda: self.run("check", {}, show), "suggested-action")
            box = self.page("Enrollment", "Use the same student ID for up to five enrollment samples.")
            self.field(box, "uid", "Student ID", "demo-student" if demo else "")
            self.field(box, "name", "Name")
            actions = self.row(box)
            self.button(actions, "Enroll sample", lambda: self.run("enroll", self.person()), "suggested-action")
            self.button(actions, "Verify student", lambda: self.run("verify", self.person()))
            box = self.page("Live class", "Open one session per lecture. Each student counts once per session.")
            self.field(box, "label", "Course, section and lecture")
            self.button(box, "Open class", lambda: self.run("open", {"label": self.get("label")},
                                                            lambda sid: self.refresh(sid)))
            if demo:
                self.field(box, "subject", "Simulated student ID", "demo-student")
            scans = self.row(box)
            self.button(scans, "Mark once", self.mark, "suggested-action")
            self.button(scans, "Start scanning", self.start_loop)
            box = self.page("Register", "Review attendance before finalizing. Later corrections issue a new signed revision.")
            self.roster_title = Gtk.Label(xalign=0, css_classes=["heading"])
            box.append(self.roster_title)
            self.search = Gtk.SearchEntry(placeholder_text=tr("Find by name or student ID"))
            self.search.update_property([Gtk.AccessibleProperty.LABEL], [tr("Find by name or student ID")])
            box.append(self.search)
            self.roster = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE, css_classes=["boxed-list"])
            box.append(self.roster)
            self.history = Gtk.Label(xalign=0, wrap=True, selectable=True)
            box.append(self.history)
            self.search.connect("search-changed", lambda *_: self.render_register())
            controls = self.row(box)
            self.button(controls, "View register", self.load_register, "suggested-action")
            self.button(controls, "Finalize class", lambda: self.confirm("Finalize class", lambda:
                        self.session_op("close", callback=lambda _: self.refresh(self.sid(), review=True))))
            self.appeal = Gtk.Expander(label=tr("Correction"))
            box.append(self.appeal)
            form = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10, margin_top=8)
            self.appeal.set_child(form)
            self.field(form, "revision", "Revision reviewed")
            self.fields["revision"].set_editable(False)
            self.selector.connect("changed", self.selection_changed)
            self.field(form, "correct_uid", "Student ID")
            self.field(form, "reason", "Appeal or correction reason")
            self.decision = self.choice(form, "Correction", ["include", "remove", "uphold"])
            self.button(form, "Issue signed revision", lambda: self.confirm("Issue signed revision", self.correct))
            box = self.page("Publication", "Give receipts to students privately. Finalize the class to share the public register or QR.")
            self.field(box, "receipt_uid", "Student ID")
            self.button(box, "Export private receipt", lambda: self.save("receipt", "private-receipt.json",
                        {"uid": self.get("receipt_uid")}))
            self.button(box, "Export public register", lambda: self.save("publish", "public-register.json"))
            self.button(box, "Show public QR", lambda: self.session_op("qr", callback=self.qr))
            box = self.page("Evaluation", "Choose a trial and record its outcome. Export the results before closing the workspace.")
            self.kind = self.choice(box, "Trial type", ["genuine", "impostor", "phone photo", "printed photo", "video replay"])
            self.field(box, "expected", "Expected student ID")
            if demo:
                self.field(box, "trial_subject", "Simulated student ID", "demo-student")
            self.button(box, "Run trial", lambda: self.run("trial", {"kind": self.kind.get_active_text(),
                        "uid": self.get("expected"), "subject": self.get("trial_subject") if demo else ""}))
            self.button(box, "Export aggregate results", lambda: self.save("metrics", "evaluation.json"))
            box = self.page("Retention", "Preview daily attendance and closed classes older than the cutoff date.")
            self.field(box, "cutoff", "Local cutoff date", placeholder="YYYY-MM-DD")
            self.show_records = self.output(box)
            self.fields["cutoff"].connect("changed", lambda *_: self.clear_preview())
            self.button(box, "Preview records", self.preview_records)
            self.button(box, "Delete previewed records", lambda: self.confirm("Delete previewed records",
                        self.purge_records), "destructive-action")
            for key in ("uid", "name", "label", "correct_uid", "reason", "receipt_uid", "expected"):
                self.fields[key].connect("changed", lambda *_: self.enable(not self.busy and not self.loop))
            if demo:
                for key in ("subject", "trial_subject"):
                    self.fields[key].connect("changed", lambda *_: self.enable(not self.busy and not self.loop))
            self.kind.connect("changed", lambda *_: self.enable(not self.busy and not self.loop))

        def clear_preview(self):
            self.preview_cutoff = None
            self.show_records("")
            self.enable(not self.busy and not self.loop)

        def preview_records(self):
            cutoff = self.get("cutoff")
            self.clear_preview()
            def display(keys):
                if self.get("cutoff") == cutoff:
                    self.preview_cutoff = cutoff if keys else None
                    self.show_records("\n".join(keys) or tr("No records before this date"))
                    self.enable(True)
            self.run("preview", {"cutoff": cutoff}, display)

        def purge_records(self):
            cutoff = self.preview_cutoff
            self.clear_preview()
            def deleted(count):
                self.refresh(message=f"{tr('Records deleted')} · {count}")
            self.run("purge", {"cutoff": cutoff}, deleted)

        def load_register(self):
            self.session_op("report", callback=self.display_register)

        def display_register(self, value):
            self.register = value
            self.fields["revision"].set_text(str(value["revision"]))
            self.render_register()
            self.enable(True)

        def selection_changed(self, *_):
            self.register = None
            self.fields["revision"].set_text("")
            self.search.set_text("")
            self.render_register()
            self.enable(not self.busy and not self.loop)

        def render_register(self):
            self.clear_roster()
            value = self.register
            self.history.set_text("")
            self.search.set_sensitive(value is not None)
            if value is None:
                self.roster_title.set_text(tr("View the register to review attendance."))
                return
            marks = value["marks"]
            self.roster_title.set_text(f"{value['label']}   ·   {len(marks)} {tr('Present')}")
            query = self.search.get_text().strip().casefold()
            for mark in marks:
                if query not in (mark["name"] + " " + mark["user_id"]).casefold():
                    continue
                row = Gtk.Box(spacing=16, css_classes=["roster-row"])
                identity = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, hexpand=True)
                identity.append(Gtk.Label(label=mark["name"], xalign=0, wrap=True, css_classes=["heading"]))
                identity.append(Gtk.Label(label=mark["user_id"], xalign=0, selectable=True))
                row.append(identity)
                times = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
                for key, label in (("local", tr("Local time")), ("utc", "UTC")):
                    stamp = mark[key].replace("T", " ", 1)
                    times.append(Gtk.Label(label=f"{label}  {stamp}", xalign=1, selectable=True))
                row.append(times)
                self.roster.append(row)
            if not self.roster.get_first_child():
                self.roster.append(Gtk.Label(label=tr("No matching students" if marks else "No attendance recorded"),
                                             css_classes=["roster-row"]))
            if value["corrections"]:
                lines = [tr("Correction history")]
                for change in value["corrections"]:
                    decision = "uphold" if change.get("upheld") else "include" if change["included"] else "remove"
                    lines.append(f"{change['time']}   {change['uid']}   {decision}   {change['reason']}")
                self.history.set_text("\n".join(lines))

        def clear_roster(self):
            while child := self.roster.get_first_child():
                self.roster.remove(child)

        def choice(self, box, label, values):
            box.append(Gtk.Label(label=tr(label), xalign=0))
            combo = Gtk.ComboBoxText()
            for value in values:
                combo.append_text(value)
            combo.set_active(0)
            box.append(combo)
            return combo

        def get(self, key):
            return self.fields[key].get_text().strip()

        def person(self):
            return {"uid": self.get("uid"), "name": self.get("name")}

        def subject(self):
            return self.get("subject") if demo else ""

        def sid(self):
            return self.selector.get_active_id()

        def refresh(self, preferred=None, *, review=False, message=None):
            previous = preferred or self.sid()
            def populate(rows):
                self.selector.remove_all()
                self.sessions = rows
                for row in rows:
                    flag = tr("Closed" if row["closed"] else "Open")
                    self.selector.append(row["id"], f"{row['label']}   [{flag}]   {row['id'][:8]}")
                if not rows:
                    self.selector.append(None, tr("No classes yet"))
                if not previous or not self.selector.set_active_id(previous):
                    self.selector.set_active(0)
                if review and self.sid():
                    self.load_register()
                elif message:
                    self.status.set_text(message)
                elif not rows:
                    self.status.set_text(tr("Open a class in Live class to start taking attendance."))
                self.enable(not self.busy and not self.loop)
            self.run("list", {}, populate)

        def correct(self):
            if not self.get("revision"):
                self.status.set_text(tr("View register"))
                return
            change = {"uid": self.get("correct_uid"), "reason": self.get("reason"),
                      "revision": self.get("revision"), "decision": self.decision.get_active_text()}
            self.selection_changed()
            self.session_op("correct", change, callback=lambda _: self.load_register())

        def session_op(self, action, args=None, callback=None):
            if not self.sid():
                self.loop = False
                self.status.set_text(tr("Select session first"))
                return
            self.run(action, {**(args or {}), "session": self.sid()}, callback)

        def mark(self):
            self.session_op("mark", {"subject": self.subject()})

        def start_loop(self):
            self.loop = True
            self.mark()

        def stop_scan(self, *_):
            self.loop = False
            if self.scan_timer is not None:
                GLib.source_remove(self.scan_timer)
                self.scan_timer = None
            if not self.busy:
                self.enable(True)
            if self.busy in ("mark", "verify", "enroll", "trial"):
                job = self.serial
                self.worker.signal(signal.SIGINT)
                def timeout():
                    if not self.closing and self.busy and self.serial == job:
                        self.worker.signal(signal.SIGKILL)
                    return False
                GLib.timeout_add(4000, timeout)
            self.cancel.set_sensitive(False)

        def confirm(self, label, invoke):
            dialog = Gtk.MessageDialog(transient_for=self, modal=True, text=tr(label) + "?")
            dialog.add_button(tr("Cancel"), Gtk.ResponseType.CANCEL)
            dialog.add_button(tr("Confirm"), Gtk.ResponseType.OK)
            def respond(d, response):
                d.destroy()
                if response == Gtk.ResponseType.OK:
                    invoke()
            dialog.connect("response", respond)
            dialog.present()

        def save(self, action, filename, extra=None):
            args = dict(extra or {})
            if action != "metrics":
                if not self.sid():
                    self.status.set_text(tr("Select session first"))
                    return
                args["session"] = self.sid()
            dialog = Gtk.FileChooserNative.new(tr("Save"), self, Gtk.FileChooserAction.SAVE, tr("Save"), tr("Cancel"))
            dialog.set_current_name(filename)
            def chosen(d, response):
                if response == Gtk.ResponseType.ACCEPT and d.get_file():
                    path = d.get_file().get_path()
                    if path:
                        self.run(action, dict(args, path=path))
                    else:
                        self.status.set_text("Choose a local destination for this export.")
                d.destroy()
            dialog.connect("response", chosen)
            dialog.show()

        def qr(self, matrix):
            window = Gtk.Window(title=tr("Show public QR"), transient_for=self)
            area = Gtk.DrawingArea()
            area.set_content_width(510)
            area.set_content_height(510)
            def draw(widget, cr, w, h):
                size = len(matrix)
                scale = max(1, min(w, h) // (size + 8))
                cr.set_source_rgb(1, 1, 1)
                cr.paint()
                cr.translate((w-size*scale)//2, (h-size*scale)//2)
                cr.set_source_rgb(0, 0, 0)
                for y, row in enumerate(matrix):
                    for x, bit in enumerate(row):
                        if bit == "1":
                            cr.rectangle(x*scale, y*scale, scale, scale)
                cr.fill()
            area.set_draw_func(draw)
            window.set_child(area)
            window.present()

        def enable(self, ready):
            ready = ready and not self.failed and not self.closing and not self.busy
            session = next((row for row in self.sessions if row["id"] == self.sid()), None)
            closed = bool(session and session["closed"])
            opened = bool(session and not closed)
            can_mark = opened and (not demo or self.subject())
            can_trial = self.kind.get_active_text() != "genuine" or self.get("expected")
            allowed = {
                "Mark once": can_mark, "Start scanning": can_mark, "Finalize class": opened,
                "View register": bool(session), "Export public register": closed, "Show public QR": closed,
                "Issue signed revision": closed and self.get("revision") and self.get("correct_uid") and self.get("reason"),
                "Export private receipt": session and self.get("receipt_uid"),
                "Open class": self.get("label"), "Enroll sample": self.get("uid") and self.get("name"),
                "Verify student": self.get("uid"), "Preview records": self.get("cutoff"),
                "Delete previewed records": self.preview_cutoff,
                "Run trial": can_trial and (not demo or self.get("trial_subject")),
            }
            self.appeal.set_sensitive(bool(ready and closed and self.get("revision")))
            for label, button in self.actions.items():
                button.set_sensitive(bool(ready and allowed.get(label, True)))
            self.selector.set_sensitive(bool(ready and self.sessions))
            self.cancel.set_sensitive(self.loop or self.busy in ("mark", "enroll", "verify", "trial"))

        def result_text(self, action, value):
            if action == "mark":
                if value == "unknown":
                    return tr("No enrolled match")
                verb = "Marked" if value["status"] == "marked" else "Already marked"
                return f"{tr(verb)} · {value['user_id']}"
            if action == "verify":
                verdict = tr("Identity verified" if value["match"] else "No identity match")
                return f"{verdict}   ·   {tr('Score')} {value['score']:.3f}"
            if action == "trial":
                verdict = {True: "Correct", False: "Incorrect", None: "Inconclusive"}[value["correct"]]
                return f"{tr(verdict)}   ·   {value['kind']}   ·   {value['reason']}   ·   {value['seconds']:.2f} s"
            if action in ("close", "correct"):
                return f"{value['label']}   ·   {tr('Revision')} {value['revision']}"
            return value if isinstance(value, str) else tr("Ready")

        def run(self, action, args, callback=None):
            if self.busy or self.closing or self.failed:
                return
            self.busy = action
            self.serial += 1
            self.enable(False)
            self.spinner.start()
            self.status.set_text(tr("Working") + "…")
            def task():
                try:
                    result = self.worker.call(action, args)
                except (OSError, EOFError, ValueError):
                    result = dict(ok=False, disconnected=True, error="Worker stopped. Restart the worker and review the register before retrying.")
                GLib.idle_add(done, result)
            def done(reply):
                if self.closing:
                    return False
                self.busy = None
                self.spinner.stop()
                if reply.get("disconnected"):
                    self.worker_failed(reply["error"])
                    return False
                if reply["ok"]:
                    value = reply["value"]
                    status = tr("Ready") if callback else self.result_text(action, value)
                    if action == "mark" and isinstance(value, dict) and value["status"] == "marked":
                        self.register = None
                        self.fields["revision"].set_text("")
                        self.render_register()
                else:
                    status = reply["error"]
                    if reply.get("reason", "operational_error") == "operational_error":
                        self.loop = False
                self.status.set_text(status)
                self.enable(not self.loop)
                if reply["ok"] and callback:
                    callback(value)
                if self.loop and action == "mark":
                    def again():
                        self.scan_timer = None
                        if self.loop and not self.closing:
                            self.mark()
                        else:
                            self.enable(True)
                        return False
                    self.scan_timer = GLib.timeout_add(1200, again)
                return False
            threading.Thread(target=task, daemon=True).start()

        def shutdown(self, *_):
            self.closing = True
            self.loop = False
            if self.scan_timer is not None:
                GLib.source_remove(self.scan_timer)
            if self.worker:
                self.worker.close()
            return False

    application = Gtk.Application(application_id="in.epics.Attendance" + ("Demo" if demo else "Teacher"),
                                  flags=Gio.ApplicationFlags.DEFAULT_FLAGS)
    def activate(app):
        if app.get_active_window():
            app.get_active_window().present()
            return
        style = Gtk.CssProvider()
        style.load_from_data(b"""
            .mode-chip { background: #184941; color: #f3fffa; padding: 4px 12px; border-radius: 14px; }
            .page-title { font-size: 1.65em; font-weight: bold; margin-bottom: 3px; }
            .page-description { margin-bottom: 8px; }
            .field-caption { font-weight: bold; }
            .workspace { background: @theme_bg_color; }
            .page-surface { background: @theme_base_color; color: @theme_text_color; padding: 20px;
                            border: 1px solid alpha(currentColor, .14); border-radius: 10px; }
            .session-bar { padding: 12px 20px; border-bottom: 1px solid alpha(currentColor, .18); }
            .status-bar { padding: 10px 16px; background: #153d39; color: #f4fffb; }
            .roster-row { padding: 8px 12px; }
            .report-output, .boxed-list { border: 1px solid alpha(currentColor, .2); border-radius: 8px; }
            button.suggested-action:not(:disabled) { background: #21675a; color: white; }
        """)
        Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), style, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        Window(app).present()
    application.connect("activate", activate)
    return application.run([])


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--hindi", action="store_true")
    options = parser.parse_args()
    try:
        sys.exit(launch(options.demo, options.hindi))
    except ImportError:
        sys.exit("Use /usr/bin/python3 with Fedora python3-gobject and gtk4 installed.")
