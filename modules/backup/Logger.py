import pandas as pd
import os
from datetime import datetime

class EventLogger:
    def __init__(self, log_path):
        self.log_path = log_path
        if os.path.exists(log_path):
            self.df = pd.read_csv(log_path)
        else:
            self.df = pd.DataFrame(columns=['timestamp', 'user', 'action', 'target', 'details'])
            self.df.to_csv(self.log_path, index=False)

    def log(self, user, action, target, details=""):
        new_event = {
            'timestamp': datetime.now(),
            'user': user,
            'action': action,
            'target': target,
            'details': details
        }
        self.df = pd.concat([self.df, pd.DataFrame([new_event])], ignore_index=True)
        self.df.to_csv(self.log_path, index=False)
