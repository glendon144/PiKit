import datetime

class Logger:
    def info(self, message):
        print(f"[INFO {datetime.datetime.now()}] {message}")

    def debug(self, message):
        print(f"[DEBUG {datetime.datetime.now()}] {message}")

    def error(self, message):
        print(f"[ERROR {datetime.datetime.now()}] {message}")

# 👇 This line makes the `log` object importable
log = Logger()

