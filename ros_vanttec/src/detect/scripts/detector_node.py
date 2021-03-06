#!/usr/bin/env python
"""
    @modified: Wed Feb 20, 2019
    @author: IngridNavarroA and fitocuan
    @file: detector_node.py
    @version: 1.0
    @brief:    
        This code implements a ROS node to perform object detection and classification 
        using YOLO detection framework and object tracking using KCF. 
        Node receives frames from 'camera' node and publishes the class, color and 
        coordinates of the detected objects. 
    @requirements: 
        Tested on python2.7
        OpenCV version 3.4+ (because it uses the "dnn" module).
        Cuda version 8.0
        Tested on ROS Kinetic. 
        Tested on Ubuntu 16.04 LTS
"""
from detection.detector import Detector 
from tracking.tracks import Object 
from tracking.tracks import Tracks 
from color.colors import *
from std_msgs.msg import String
from imutils.video import VideoStream
from imutils.video import FPS

import imutils
import numpy as np 
import time
import rospy
import cv2

DEBUG = 1

def send_message(color, msg, node="detector"):
    """ Publish message to ros node. """
    assert node == "detector" or node == "info", \
        Color.RED + "[ERROR] unsupported node." + Color.DONE

    msg = color + msg + Color.DONE
    rospy.loginfo(msg)

    if node == "detector":
        detector_pub.publish(msg)
    elif node == "info":
        infomsg_pub.publish(msg)

def detect(config, weights, classes, video):
    """ Performs object detection and publishes a data structure that contains, instance 
        coordinates, instance class and sets a counter that will be used by the tracker. 
    """

    # Initialize detector 
    send_message(Color.GREEN, "[INFO] Initializing TinyYOLOv3 detector.", "info")
    det = Detector(config, weights, classes)
    (H, W) = (None, None)

    # Initialize object tracks
    tracks = Tracks()

    # Initilialize Video Stream
    send_message(Color.GREEN, "[INFO] Starting video stream.", "info")
    if video == "0":
        video = cv2.VideoCapture(0)
    else:
        video = cv2.VideoCapture(args.video)

    counter, N = 0, 12
    detect = True
    fps = FPS().start()
    
    while not rospy.is_shutdown() or video.isOpened():
        # Grab next frame
        ret, frame = video.read()

        if not ret:
            send_message(Color.RED, "[DONE] Finished processing.", "info")
            cv2.waitKey(2000)
            break
        elif cv2.waitKey(1) & 0xFF == ord ('q'):
            send_message(Color.RED, "[DONE] Quitting program.", "info")
            break

        frame = imutils.resize(frame, width=1000)
        (H, W) = frame.shape[:2]
        if det.get_width() is None or det.get_height() is None:
            det.set_height(H)
            det.set_width(W)

        # Modify frame brightness if necessary
        # frame = change_brightness(frame, 0.8) # Decrease
        # frame = change_brightness(frame, 1.5) # Increase

      	# Every N frames perform detection
        if detect:
            # boxes, indices, cls_ids = [], [], []
        	boxes, indices, cls_ids = det.get_detections(det.net, frame)
        	print(len(boxes))
        	objects = []
        	# Create objects and update tracks
        	for i in range(len(cls_ids)):
        		x, y, w, h = boxes[i]
        		# Create object with attributes: class, color, bounding box
        		obj = Object(cls_ids[i], 
                            get_color(frame, x, y, w, h), 
        					boxes[i], 
                            cv2.TrackerKCF_create())
        		obj.tracker.init(frame, (x, y, w, h))
        		objects.append(obj)
        	tracks.update(objects)
        	detect = False
        # While counter < N, update through KCF
        else:
            if counter == N:
                counter = 0
                detect = True

            for o in tracks.objects:
                obj = tracks.get_object(o)
                obj.print_object()
                (succ, bbox) = obj.update_tracker(frame)
                if not succ:
                    obj.reduce_lives()
                    if obj.get_lives() == 0:
                        tracks.delete_object(o)
                else:
                    obj.update_object_bbox(bbox)
                    obj.reset_lives()
                    tracks.set_object(obj, o)

        # This is for debugging purposes. Just to check that bounding boxes are updating. 
        if DEBUG:
            for o in tracks.objects:
                obj = tracks.get_object(o)
                x, y, w, h = obj.get_object_bbox()
                det.draw_prediction(frame, obj.get_class(), obj.get_color(), obj.get_id(), int(x), int(y), int(x+w), int(y+h))
        
        # Publish detections
        counter += 1
        det_str = "Detections {}: {}".format(counter, tracks.objects)
        send_message(Color.BLUE, det_str)

        fps.update()
        fps.stop()

        info = [
            ("FPS", "{:.2F}".format(fps.fps())),
            ("OUT", "class, color, id")
        ]
        for (i, (k, v)) in enumerate(info):
            text = "{}: {}".format(k, v)
            cv2.putText(frame, text, (10, det.get_height() - ((i * 20) + 20)), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)

        # Show current frame
        cv2.imshow("Frame", frame)
        rate.sleep()

if __name__ == '__main__':
    import argparse

    # Parse arguments
    ap = argparse.ArgumentParser()
    ap.add_argument('--config',  required=True, help = 'Path to yolo config file')
    ap.add_argument('--weights', required=True, help = 'Path to yolo pre-trained weights')
    ap.add_argument('--classes', required=True, help = 'Path to text file containing class names')
    ap.add_argument('--video',   required=True, help = 'Path to the video' )
    args = ap.parse_args()

    try:
        # Create publisher 
        infomsg_pub = rospy.Publisher('infomsg', String, queue_size=10)
        detector_pub = rospy.Publisher('detections', String, queue_size=10)
        rospy.init_node('detector')
        rate = rospy.Rate(10) # 10Hz
        detect(args.config, args.weights, args.classes, args.video)
    
    except rospy.ROSInterruptException:
        print("[ERROR] Interrupted. ")
        exit()