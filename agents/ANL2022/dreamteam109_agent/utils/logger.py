from tudelft_utilities_logging.ReportToLogger import ReportToLogger

class Logger:

    def __init__(self, base_logger: ReportToLogger, id: int):
        self.base_logger = base_logger
        self.id = id

    def log(self, level:int , msg:str, thrown: BaseException=None) -> None:
        self.base_logger.log(level, f"{self.id} - {msg}", thrown)
