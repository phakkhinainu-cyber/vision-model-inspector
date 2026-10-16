import multiprocessing
import sys

if __name__ == "__main__":
    multiprocessing.freeze_support()  # จำเป็นสำหรับ process กล้องในไฟล์ .exe
    from lpr.__main__ import main

    sys.exit(main())
