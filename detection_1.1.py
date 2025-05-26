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

    def new_function(self):  # New function example
        return "The meaning of life is: "

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
    count = user_data.get_count() # << 추가된 부분: 현재 프레임 카운트를 시간 대용으로 사용
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
    danger_3 = 70 #danger level threshold
    danger_2 = 10
    danger_1 = 3
    current_frame_track_ids = set() # << 추가된 부분: 현재 프레임의 활성 트랙 ID 관리용
    
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
        overlap = 100.0*(box_width*box_height)/(width*height)
        
        prev_box_width = box_width #previous box width
        prev_box_height = box_height #previous box height
        if label == "mouse":
            detection_count += 1
            # Get track ID
            track_id = 0
            track = detection.get_objects_typed(hailo.HAILO_UNIQUE_ID)
            if len(track) == 1:
                track_id = track[0].get_id()
                current_frame_track_ids.add(track_id) # << 추가된 부분
            string_to_print += f"ID: {track_id}, Conf: {confidence:.2f}, Overlap: {overlap:.2f}%\n"

           # --- ▼▼▼ 핵심 추가 로직: 객체 상태 추적 및 분석 ▼▼▼ ---
            if track_id in user_data.previous_detections: # << 추가된 조건문: 이전 정보가 있는지 확인
                prev_info = user_data.previous_detections[track_id]
                prev_overlap = prev_info['overlap']
                prev_frame_time = prev_info['frame_time']

                delta_time = current_frame_time - prev_frame_time

                if delta_time > 0: 
                    delta_overlap = overlap - prev_overlap
                    overlap_velocity = delta_overlap / delta_time 

                    status = ""
                    # 임계값은 실험을 통해 조정 필요
                    if delta_overlap > 0.1: 
                        status = f"Approaching (Rate: {overlap_velocity:+.2f} %/frame)"
                    elif delta_overlap < -0.1: 
                        status = f"Receding (Rate: {overlap_velocity:+.2f} %/frame)"
                    else:
                        status = "Stationary (or minor change)"
                    string_to_print += f"    └ Status: {status}\n"

                    if frame is not None: # 프레임에 상태 정보 그리기
                         cv2.putText(frame, f"ID:{track_id} {status}", (xmin, ymin - 10), 
                                     cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 1)

            user_data.previous_detections[track_id] = {
                'overlap': overlap,
                'frame_time': current_frame_time,
                'bbox': bbox 
            }
            
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
    elif overlap > danger_2 :
        danger = 2 # warning
    elif overlap > danger_1 :
        danger = 1 # on list
    else :
        danger = 0
    print(f"danger = {danger}")
        
    return Gst.PadProbeReturn.OK

if __name__ == "__main__":
    # Create an instance of the user app callback class
    user_data = user_app_callback_class()
    app = GStreamerDetectionApp(app_callback, user_data)
    app.run()
