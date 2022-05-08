# Copyright (c) Microsoft. All rights reserved.
# Licensed under the MIT license. See LICENSE file in the project root for
# full license information.

import asyncio
import sys
import signal
import threading
from azure.iot.device.aio import IoTHubModuleClient
#------------------------------------------------------------------------------
#Added by thesis author
import struct
import wave
import json
from datetime import datetime
import numpy
import time
from azure.storage.blob import BlobServiceClient
import io
#------------------------------------------------------------------------------


# Event indicating client stop
stop_event = threading.Event()
#------------------------------------------------------------------------------
#Added by thesis author
properties = {
    "test": {
        "frequency": 44100,
        "block_size": 1024,
        "storage_limit": 100,
        "max_block_separation": 0.1,
        "width": 2
    }
}
use_blob = True
counter_temp = 0
temp_data = {}

def save_wav(list_of_blocks, filename):
    samples = [item for items in list_of_blocks for item in items]
    with wave.open("/storage/"+filename+".wav", "w") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(properties["test"]["frequency"])
        for sample in samples:
            converted = numpy.array(sample)*32768
            converted = converted.astype(numpy.int16)
            f.writeframes(struct.pack("h", converted)) #test maybe "<h"

def blob_setup():
    endpoint_protocol = "https"
    blob_endpoint = "<local_module_endpoint>"
    account_name = "<local_account_name>"
    account_key = "<local_account_key>"
    connection_string = "DefaultEndpointsProtocol="+endpoint_protocol+";BlobEndpoint="+blob_endpoint+";AccountName="+account_name+";AccountKey="+account_key
    blob_service_client = BlobServiceClient.from_connection_string(connection_string)
    container = blob_service_client.get_container_client("cont1")
    if container.exists():
        pass
    else:
        container.create_container()
    return container

def save_blob(list_of_blocks, filename, container):
    data_container = io.BytesIO()
    blob_name = filename+".wav"
    samples = [item for items in list_of_blocks for item in items]
    with wave.open(data_container, "wb") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(properties["test"]["frequency"])
        for sample in samples:
            converted = numpy.array(sample)*32768
            converted = converted.astype(numpy.int16)
            f.writeframes(struct.pack("h", converted))
    data_container.seek(0)
    container.upload_blob(blob_name, data_container)
#------------------------------------------------------------------------------


def create_client():
    client = IoTHubModuleClient.create_from_edge_environment()

#------------------------------------------------------------------------------
#Added by thesis author
    if use_blob:
        container = blob_setup()
#------------------------------------------------------------------------------

    # Define function for handling received messages
    async def receive_message_handler(message):
        # NOTE: This function only handles messages sent to "input1".
        # Messages sent to other inputs, or to the default, will be discarded
        if message.input_name == "input1":
            print("the data in the message received on input1 was ")
            print(message.data)
            print("custom properties are")
            print(message.custom_properties)
            print("NOT forwarding mesage to output1")
            #await client.send_message_to_output(message, "output1")
#------------------------------------------------------------------------------
#Added by thesis author
        elif message.input_name == "storage":
            #Used for testing. Takes a single list of list of data and saves
            global counter_temp
            converted_message = json.loads(message.data)
            blocks = converted_message['data']
            save_wav(blocks, str(counter_temp))
            counter_temp = counter_temp + 1
        elif message.input_name == "blocks":
            converted_message = json.loads(message.data)
            if converted_message['request_id'] in temp_data.keys():
                temp_data[converted_message['request_id']]['data'].extend(converted_message['data'])
            else:
                temp_data[converted_message['request_id']] = {
                    'sensor_id': converted_message['sensor_id'],
                    "start_time": datetime.fromisoformat(converted_message['start_time']),
                    'data': converted_message['data']
                }
            if converted_message['message_counter'] == converted_message['message_total']:
                if use_blob:
                    save_blob(
                        temp_data[converted_message['request_id']]['data'], 
                        datetime.isoformat(temp_data[converted_message['request_id']]['start_time']),
                        container
                    )
                else:
                    save_wav(
                        temp_data[converted_message['request_id']]['data'], 
                        datetime.isoformat(temp_data[converted_message['request_id']]['start_time'])
                    )
                temp_data.pop(converted_message['request_id'], None)
#------------------------------------------------------------------------------
        else:
            print("No matching input")

    try:
        # Set handler on the client
        client.on_message_received = receive_message_handler
    except:
        # Cleanup if failure occurs
        client.shutdown()
        raise

    return client


async def run_sample(client):
    # Customize this coroutine to do whatever tasks the module initiates
    # e.g. sending messages
    while True:
        await asyncio.sleep(10)


def main():
    if not sys.version >= "3.5.3":
        raise Exception( "The sample requires python 3.5.3+. Current version of Python: %s" % sys.version )
    print ( "IoT Hub Client for Python" )

    # NOTE: Client is implicitly connected due to the handler being set on it
    client = create_client()

    # Define a handler to cleanup when module is is terminated by Edge
    def module_termination_handler(signal, frame):
        print ("IoTHubClient sample stopped by Edge")
        stop_event.set()

    # Set the Edge termination handler
    signal.signal(signal.SIGTERM, module_termination_handler)

    # Run the sample
    loop = asyncio.get_event_loop()
    try:
        loop.run_until_complete(run_sample(client))
    except Exception as e:
        print("Unexpected error %s " % e)
        raise
    finally:
        print("Shutting down IoT Hub Client...")
        loop.run_until_complete(client.shutdown())
        loop.close()


if __name__ == "__main__":
    main()
