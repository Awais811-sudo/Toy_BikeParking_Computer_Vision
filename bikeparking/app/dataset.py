from roboflow import Roboflow

rf = Roboflow(api_key="tCfryfXq71YKtku6OPE5")
project = rf.workspace("fyp-project-rjniu").project("toy-bike-parking-g1nhx")
dataset = project.version(1).download("yolov8")  # or 'yolov5' if preferred
