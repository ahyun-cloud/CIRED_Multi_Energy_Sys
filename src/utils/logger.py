"""
logger.py - 표준 로깅 설정 (파일 + 콘솔 동시 출력)

사용법:
    from src.utils.logger import setup_logger
    logger = setup_logger("cired", log_file="outputs/cired/run.log")
    logger.info("모델 풀이 시작")
"""

import logging
from pathlib import Path


def setup_logger(name: str, log_file=None, level=logging.INFO) -> logging.Logger:
    """파일 + 콘솔 동시 출력 로거 생성."""
    logger = logging.getLogger(name)
    logger.setLevel(level)
    logger.handlers = []        # 중복 핸들러 방지
    logger.propagate = False

    formatter = logging.Formatter(
        "[%(asctime)s] %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    if log_file:
        log_file = Path(log_file)
        log_file.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    return logger
