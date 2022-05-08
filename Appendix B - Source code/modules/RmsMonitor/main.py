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
import numpy
import json
import datetime
from azure.iot.device.iothub.models.message import Message
import os
#------------------------------------------------------------------------------

# Event indicating client stop
stop_event = threading.Event()

#------------------------------------------------------------------------------
#Added by thesis author
def rms_from_list(list):
    return numpy.sqrt(numpy.mean(numpy.array(list)**2))

max_calculated_rms = 0
#------------------------------------------------------------------------------


def create_client():
    client = IoTHubModuleClient.create_from_edge_environment()

    # Define function for handling received messages
    async def receive_message_handler(message):
        # NOTE: This function only handles messages sent to "input1".
        # Messages sent to other inputs, or to the default, will be discarded
#------------------------------------------------------------------------------
#Added by thesis author
        if message.input_name == "stream":
            global max_calculated_rms
            converted_message = json.loads(message.data)
            converted_time = datetime.datetime.fromisoformat(converted_message['timestamp'])
            rms = rms_from_list(converted_message['data'])
            if rms > max_calculated_rms:
                max_calculated_rms = rms
                output_data = json.dumps({
                        'event': "RMS threshold crossed",
                        'sensor_id': converted_message['sensor_id'],
                        'timestamp': converted_message['timestamp'],
                        'rms': rms
                    })
                output_message = Message(output_data)
                await client.patch_twin_reported_properties({"max_calculated_rms": max_calculated_rms})
                
                sensor_id = converted_message['sensor_id']
                start_time = converted_message['timestamp'] #datetime.datetime.now(datetime.timezone.utc)-datetime.timedelta(seconds=1)
                end_time = converted_message['timestamp']
                payload = json.dumps({
                    'sensor_id': sensor_id,
                    'start_time': start_time, #datetime.datetime.isoformat(start_time)
                    'end_time': end_time#datetime.datetime.isoformat(end_time)
                })
                method_params={#Should contain a methodName (str), payload (str), connectTimeoutInSeconds (int), responseTimeoutInSeconds (int)
                    'methodName': "GetDataSlice",#Accesible in method
                    'payload': payload,#Accesible in method
                    'connectTimeoutInSeconds':1,
                    'responseTimeoutInSeconds':10 #Between 5 and 300
                }
                await client.invoke_method(method_params, os.environ["IOTEDGE_DEVICEID"], "LoggingController")
                await client.send_message_to_output(output_message, "alert")

    async def receive_twin_patch_handler(twin_patch):
        global max_calculated_rms
        try:
            max_calculated_rms = twin_patch['max_calculated_rms']
        except Exception as e:
            pass
        await client.patch_twin_reported_properties({"max_calculated_rms": max_calculated_rms})
#------------------------------------------------------------------------------

    try:
        # Set handler on the client
        client.on_message_received = receive_message_handler
#------------------------------------------------------------------------------
#Added by thesis author
        client.on_twin_desired_properties_patch_received = receive_twin_patch_handler
#------------------------------------------------------------------------------
    except:
        # Cleanup if failure occurs
        client.shutdown()
        raise

    return client

#------------------------------------------------------------------------------
#Added by thesis author
async def get_twin(client):
    global max_calculated_rms
    module_properties = await client.get_twin()
    try:
        max_calculated_rms = module_properties['desired']['max_calculated_rms']
    except Exception as e:
        pass
    await client.patch_twin_reported_properties({"max_calculated_rms": max_calculated_rms})
#------------------------------------------------------------------------------


async def run_sample(client):
    # Customize this coroutine to do whatever tasks the module initiates
    # e.g. sending messages
    while True:
        await asyncio.sleep(1000)


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
#------------------------------------------------------------------------------
#Added by thesis author
    asyncio.run(get_twin(client))
#------------------------------------------------------------------------------
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
