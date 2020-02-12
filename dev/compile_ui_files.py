"""Converts every ui-file in views/ui to a py-file in views/gen."""
import os
from PyQt5 import uic


if __name__ == "__main__":
    PATH = os.getcwd().replace("dev", "")
    os.chdir(PATH)
    for file in os.listdir("uaclient"):
        if not file.endswith(".ui"):
            continue
        print("Converting file {}".format(file))
        new_file = file.replace(".ui", ".py")
        with open(os.path.join("uaclient", file), "r") as source:
            with open(os.path.join("uaclient", new_file), "w") as target:
                uic.compileUi(source, target)
    print("Conversion finished")
