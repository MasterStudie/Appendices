# Copyright (c) Microsoft. All rights reserved.
# Licensed under the MIT license. See LICENSE file in the project root for
# full license information.

import asyncio
from math import ceil, floor
import sys
import signal
import threading
from azure.iot.device.aio import IoTHubModuleClient
#------------------------------------------------------------------------------
#Added by thesis author
from azure.iot.device.iothub.models.methods import MethodResponse
import numpy
from datetime import datetime, timezone, timedelta
import json
from collections import deque
import itertools

class SensorData():
    def __init__(self, sensor_params) -> None:
        self.frequency = sensor_params['frequency']
        self.block_size = sensor_params['block_size']
        self.storage_limit = sensor_params['storage_limit'] # Number of blocks
        self.max_block_separation = sensor_params['max_block_separation']
        self.max_block_per_message = sensor_params['max_block_per_message']
        self.data = deque(maxlen=self.storage_limit)
        self.timestamps = deque(maxlen=self.storage_limit)
        self.stream = sensor_params['stream']

    def put_data(self, timestamp, data_block):
        if self.timestamps:
            if ((timestamp - self.timestamps[-1]).seconds > self.max_block_separation):
                self.data.clear()
                self.data.append(data_block)
                self.timestamps.clear()
                self.timestamps.append(timestamp)
            else:
                self.data.append(data_block)
                self.timestamps.append(timestamp)
        else:
            self.data.append(data_block)
            self.timestamps.append(timestamp)

    def find_start(self, deq, start):
        i = 0
        found = False
        for log_time in deq:
            if log_time >= start:
                found = True
                return i
            i += 1
        return -1

    def find_stop(self, deq, stop):
        i = 0
        found = False
        for log_time in deq:
            if log_time > stop:
                found = True
                return i
            i += 1
        return -1

    def get_data(self, start_time, end_time):
        if len(self.timestamps)==0:
            return None, None, None
        else:
            start_index = self.find_start(self.timestamps, start_time)
            if start_index == -1:
                return None, None, None
            else:
                stop_index = self.find_stop(self.timestamps, end_time)
                if stop_index == -1:
                    stop_index = len(self.timestamps)
                data = list(itertools.islice(self.data, start_index, stop_index))
                return data, self.timestamps[start_index], self.timestamps[stop_index-1]

class TemporaryData():
    def __init__(self, sensors) -> None:
        self.sensors = {}
        for sensor in sensors:
            self.sensors[sensor] = SensorData(sensors[sensor])

    def store_data(self, sensor, data, timestamp):
        self.sensors[sensor].put_data(timestamp, data)

    def retreive_data(self, sensor, start_time, end_time):
        data, found_start, found_stop = self.sensors[sensor].get_data(start_time, end_time)
        return data, found_start, found_stop
#------------------------------------------------------------------------------
#------------------------------------------------------------------------------
#Added by thesis author, based on work by:
#Code author: tixxit
#Code source: https://stackoverflow.com/questions/2130016/splitting-a-list-into-n-parts-of-approximately-equal-length
def split(a, n):
    k, m = divmod(len(a), n)
    return (a[i*k+min(i, m):(i+1)*k+min(i+1, m)] for i in range(n))
#------------------------------------------------------------------------------

# Event indicating client stop
stop_event = threading.Event()

#------------------------------------------------------------------------------
#Added by thesis author
temporary_data = TemporaryData({
        "test": {
            "frequency": 44100,
            "block_size": 1024,
            "storage_limit": 49,
            "max_block_separation": 1,
            "max_block_per_message": floor((256000 / 17)/4410) - 1,
            "stream": True
        }
    })
#------------------------------------------------------------------------------

def create_client():
    client = IoTHubModuleClient.create_from_edge_environment()

    # Define function for handling received messages
    async def receive_message_handler(message):
        # NOTE: This function only handles messages sent to "input1".
        # Messages sent to other inputs, or to the default, will be discarded
#------------------------------------------------------------------------------
#Added by thesis author
        if message.input_name == "sensor":
            converted_message = json.loads(message.data)
            converted_time = datetime.fromisoformat(converted_message['timestamp'])
            temporary_data.store_data(converted_message['sensor_id'], converted_message['data'], converted_time)
            if temporary_data.sensors[converted_message['sensor_id']].stream:
                await client.send_message_to_output(message.data, "stream")
#------------------------------------------------------------------------------
        else:
            print("the data in the message received on unknown input was ")
            print(message.data)
            print("custom properties are")
            print(message.custom_properties)

#------------------------------------------------------------------------------
#Added by thesis author
    async def receive_method_handler(method_request):
        method = method_request.name
        payload = json.loads(method_request.payload)
        if method == "GetDataSlice":
            sensor = payload['sensor_id']
            start_time = datetime.fromisoformat(payload['start_time'])
            end_time = datetime.fromisoformat(payload['end_time'])
            request_id = method_request.request_id
            result, found_start, found_end = temporary_data.retreive_data(sensor, start_time, end_time)
            if result == None:
                print("Ingen data returnert:")
            else:
                number_of_blocks = len(result)
                if number_of_blocks == 0:
                    number_of_blocks = 1
                number_of_messages = ceil(number_of_blocks/temporary_data.sensors[sensor].max_block_per_message)
                split_data = list(split(result,number_of_messages))
                i = 1
                for data_content in split_data:
                    data_payload = json.dumps({
                        'data': data_content, 
                        "start_time": datetime.isoformat(found_start), 
                        "end_time": datetime.isoformat(found_end), 
                        'sensor_id': sensor, 
                        'message_counter': i,
                        'request_id': request_id,
                        'message_total': number_of_messages
                    })
                    await client.send_message_to_output(data_payload, "requested")
                    i += 1
        else:
            print("No matching method")
        await client.send_method_response(MethodResponse(method_request.request_id, 0, payload = None))
    
#------------------------------------------------------------------------------

    try:
        # Set handler on the client
        client.on_message_received = receive_message_handler
#------------------------------------------------------------------------------
#Added by thesis author
        client.on_method_request_received = receive_method_handler
#------------------------------------------------------------------------------
    except:
        # Cleanup if failure occurs
        client.shutdown()
        raise

    return client


async def run_sample(client):
    # Customize this coroutine to do whatever tasks the module initiates
    # e.g. sending messages
    #while True:
    while not stop_event.is_set():
        await asyncio.sleep(10)

#------------------------------------------------------------------------------
#Added by thesis author
async def check_twin(client):
    module_properties = await client.get_twin()
    properties = {
        "test": {
            "frequency": 44100,
            "block_size": 1024,
            "storage_limit": 100,
            "max_block_separation": 0.1
        }
    }
    global temporary_data
    temporary_data = TemporaryData(sensors=properties)
#------------------------------------------------------------------------------

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
        print("starting main loop...")
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
