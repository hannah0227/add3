import gi
gi.require_version('Gst', '1.0')
from gi.repository import Gst, GLib
import os
import numpy as np
import cv2
import hailo

from hailo_apps_infra.hailo_rpi_common import (
    get_caps_from_pad,
    get_numpy_from_buffer,
    app_callback_class,
)
from hailo_apps_infra.detection_pipeline import GStreamerDetectionApp

# -----------------------------------------------------------------------------------------------
# User-defined class to be used in the callback function
# -----------------------------------------------------------------------------------------------
# Inheritance from the app_callback_class
class user_app_callback_class(app_callback_class):
    def __init__(self):
        super().__init__()
        self.new_variable = 42  # New variable example
        self.prev_overlap = 0.0 #<<<<<<<<<<<<<<<<<<<<<<<<

# -----------------------------------------------------------------------------------------------
# User-defined callback function
# -----------------------------------------------------------------------------------------------

# This is the callback function that will be called when data is available from the pipeline
def app_callback(pad, info, user_data):
    # Get the GstBuffer from the probe info
    buffer = info.get_buffer()
    # Check if the buffer is valid
    if buffer is None:
        return Gst.PadProbeReturn.OK

    # Using the user_data to count the number of frames
    user_data.increment()
    count = user_data.get_count()
    string_to_print = f"Frame count: {user_data.get_count()}\n"

    # Get the caps from the pad
    # get size of camera resolution
    format, width, height = get_caps_from_pad(pad)

    # If the user_data.use_frame is set to True, we can get the video frame from the buffer
    frame = None
    if user_data.use_frame and format is not None and width is not None and height is not None:
        # Get video frame
        frame = get_numpy_from_buffer(buffer, format, width, height)

    # Get the detections from the buffer
    roi = hailo.get_roi_from_buffer(buffer)
    detections = roi.get_objects_typed(hailo.HAILO_DETECTION)

    # Parse the detections
    detection_count = 0
    danger_3 = 50 #danger level threshold
    danger_2 = 10
    danger_1 = 3

    current_frames_last_overlap = 0.0 #<<<<<<<<<<<<<<<<<<<<<<
    
    for detection in detections:
        danger = 0 # danger level 
        label = detection.get_label()
        bbox = detection.get_bbox()
        confidence = detection.get_confidence()
        
        # get bouding box coordinates , erasable
        xmin, ymin, xmax, ymax = int(width*bbox.xmin()), int(height*bbox.ymin()), int(width*bbox.xmax()), int(height*bbox.ymax())
        
        # calculate variations from coordinates
        box_width = xmax - xmin 
        box_height = ymax - ymin
        overlap = 100*(box_width*box_height)/(width*height)
        
        current_frames_last_overlap = overlap #<<<<<<<<<<<<<<<<<<<<<<

        if label == "mouse":
            # Get track ID
            track_id = 0
            track = detection.get_objects_typed(hailo.HAILO_UNIQUE_ID)
            if len(track) == 1:
                track_id = track[0].get_id()
            string_to_print += (f"Detection: ID: {track_id} Label: {label} Confidence: {confidence:.2f}\n")
            detection_count += 1


    if current_frames_last_overlap > user_data.prev_overlap:
        if current_frames_last_overlap - user_data.prev_overlap > 10:
            print("very fast approaching \n")
        elif current_frames_last_overlap - user_data.prev_overlap > 5:
            print("fast approaching \n")
        else:
            print("approaching \n")
    elif current_frames_last_overlap < user_data.prev_overlap:
        print("moving away \n")
    else:
        print("no change \n")
    
    # Update prev_overlap in user_data for the next frame's comparison
    user_data.prev_overlap = current_frames_last_overlap
    
    if user_data.use_frame:
        # Note: using imshow will not work here, as the callback function is not running in the main thread
        # Let's print the detection count to the frame
        cv2.putText(frame, f"Detections: {detection_count}", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
        # Example of how to use the new_variable and new_function from the user_data
        # Let's print the new_variable and the result of the new_function to the frame
        cv2.putText(frame, f"{user_data.new_function()} {user_data.new_variable}", (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
        # Convert the frame to BGR
        frame = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
        user_data.set_frame(frame)

    print(string_to_print)
    #this is kick
    print(f"overlap: {overlap, box_width,box_height}")

    if overlap > danger_3 :
        danger = 3  # collision!
        print ("very close, ")
    elif overlap > danger_2 :
        danger = 2 # warning
        print ("close, ")
    elif overlap > danger_1 :
        danger = 1 # on list
        print ("moderate, ")
    else :
        danger = 0
        print ("far, ")
    print(f"danger = {danger}")
        
    return Gst.PadProbeReturn.OK

if __name__ == "__main__":
    # Create an instance of the user app callback class
    user_data = user_app_callback_class()
    app = GStreamerDetectionApp(app_callback, user_data)
    app.run()
