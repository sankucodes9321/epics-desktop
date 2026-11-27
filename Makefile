PY = .venv/bin/python
USER_ID ?= alice

.PHONY: setup-demo setup test test-desktop test-storage doctor prefetch audit clean
setup:
	test -x $(PY) || python3.11 -m venv .venv
	$(PY) -m pip install torch==2.6.0 --index-url https://download.pytorch.org/whl/cpu
	$(PY) -m pip install -r requirements.txt
setup-demo:
	test -x $(PY) || python3.11 -m venv .venv
	$(PY) -m pip install -r requirements-demo.txt
test:
	$(PY) -m pytest -q
test-desktop:
	/usr/bin/python3 tests/gtk_smoke.py
test-storage:
	$(PY) -m pytest -q -m live tests/test_classroom_integration.py
doctor:
	$(PY) -m scripts.doctor
prefetch:
	$(PY) -m scripts.prefetch_models
audit:
	$(PY) -m scripts.audit_no_disk_writes --user-id "$(USER_ID)"
clean:
	find privacy scripts tests -depth \( -type f \( -name '*.pyc' -o -name '*.pyo' \) -o -type d -name __pycache__ -empty \) -delete
	if test -d __pycache__; then find __pycache__ -depth \( -type f -name '*.py[co]' -o -type d -empty \) -delete; fi
	if test -d .pytest_cache; then find .pytest_cache -depth -delete; fi

.PHONY: teacher teacher-demo verifier
teacher:
	/usr/bin/python3 teacher_app.py
teacher-demo:
	/usr/bin/python3 teacher_app.py --demo
verifier:
	/usr/bin/python3 student_verifier.py
