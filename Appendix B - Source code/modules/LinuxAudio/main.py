# Copyright (c) Microsoft. All rights reserved.
# Licensed under the MIT license. See LICENSE file in the project root for
# full license information.

import asyncio
import sys
import signal
import threading
from time import time, sleep
from azure.iot.device.aio import IoTHubModuleClient
#------------------------------------------------------------------------------
#Added by thesis author
from numpy import frombuffer
from datetime import datetime, timezone
from azure.iot.device.iothub.models.message import Message
import json
#------------------------------------------------------------------------------

# Event indicating client stop
stop_event = threading.Event()
#------------------------------------------------------------------------------
#Added by thesis author
stop_execution = threading.Event()
local_twin = {}

def update_twin_data(patch):
    local_twin['sensor_id'] = patch['sensor_id']
    local_twin['daq_log'] = patch['daq_log']
    local_twin['audio_device_index'] = patch['audio_device_index']
    local_twin['width'] = patch['width']
    local_twin['channels'] = patch['channels']
    local_twin['rate'] = patch['rate']
    local_twin['block_size'] = patch['block_size']
#------------------------------------------------------------------------------


def create_client():
    client = IoTHubModuleClient.create_from_edge_environment()

    # Define function for handling received messages
    async def receive_message_handler(message):
        # NOTE: This function only handles messages sent to "input1".
        # Messages sent to other inputs, or to the default, will be discarded
        if message.input_name == "input1":
            print("the data in the message received on input1 was ")
            print(message.data)
            print("custom properties are")
            print(message.custom_properties)
            print("forwarding mesage to output1")
            await client.send_message_to_output(message, "output1")

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
        await asyncio.sleep(1000)


#------------------------------------------------------------------------------
#Added by thesis author, based on work by:
#Code author: user4815162342
#Code source: https://stackoverflow.com/questions/53993334/converting-a-python-function-with-a-callback-to-an-asyncio-awaitable
pa = pyaudio.PyAudio()
def make_iter():
    loop = asyncio.get_event_loop()
    queue = asyncio.Queue()
    def put(*args):
        loop.call_soon_threadsafe(queue.put_nowait, args)
        return (args[0], pyaudio.paContinue)
    async def get():
        while not stop_execution.is_set():
            yield await queue.get()
    return get(), put

async def main_audio(client, ready_event):
    while not stop_event.is_set():
        await ready_event.wait()
        if not stop_execution.is_set():
            try:
                stream_get, stream_put = make_iter()
                stream = pa.open(
                        format=pa.get_format_from_width(local_twin['width']),
                        channels=local_twin['channels'],
                        rate=local_twin['rate'],
                        frames_per_buffer=local_twin['block_size'],
                        stream_callback=stream_put,
                        input=True,
                        input_device_index=local_twin['audio_device_index']
                    )
                stream.start_stream()
                await client.patch_twin_reported_properties({"status": "Logging data"})
                async for in_data, frame_count, time_info, status in stream_get:
                    data = frombuffer(in_data, 'h')
                    if local_twin['width'] == 2:
                        scaled_data = data / 32768.0
                    else:
                        scaled_data = data
                    output_data = json.dumps({
                        'sensor_id': local_twin['sensor_id'],
                        'timestamp': datetime.isoformat(datetime.now(timezone.utc)),
                        'data': scaled_data.tolist()
                    })
                    output_message = Message(output_data)
                    await client.send_message_to_output(output_message, "sensor")
                stream.close()
                await client.patch_twin_reported_properties({"status": "Not logging"})

            except Exception as e:
                ready_event.clear()
                stop_execution.clear()
                await client.patch_twin_reported_properties({"status": str(e)})
        else:
            print("Ready with stop in execution")
    else:
        print("Module function finished")

async def check_twin(client):
    module_properties = await client.get_twin()
    desired_twin = module_properties['desired']
    update_twin_data(desired_twin)

async def get_available_devices(client):
    available_devices = {}
    for i in range(pa.get_device_count()):
        available_devices[str(i)] = pa.get_device_info_by_index(i).get('name')
    await client.patch_twin_reported_properties({"availableDevices": available_devices})

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
        stop_execution.set()

    # Set the Edge termination handler
    signal.signal(signal.SIGTERM, module_termination_handler)

    # Run the sample
    loop = asyncio.get_event_loop()
#------------------------------------------------------------------------------
#Added by thesis author
    asyncio.run(check_twin(client))
    asyncio.run(get_available_devices(client))
    module_ready = asyncio.Event(loop=loop)
    if local_twin['daq_log']:
        stop_execution.clear()
        module_ready.set()
    else:
        module_ready.clear()
        stop_execution.set()

    # Function for receiveing twin patchers:
    async def receive_twin_patch_handler(twin_patch):
        update_twin_data(twin_patch)
        if local_twin['daq_log']:
            stop_execution.clear()
            module_ready.set()
        else:
            module_ready.clear()
            stop_execution.set()
        await client.patch_twin_reported_properties(local_twin)

    client.on_twin_desired_properties_patch_received = receive_twin_patch_handler
#------------------------------------------------------------------------------
    try:
        #loop.run_until_complete(run_sample(client))
#------------------------------------------------------------------------------
#Added by thesis author
        loop.run_until_complete(main_audio(client, module_ready))
#------------------------------------------------------------------------------
    except Exception as e:
        print("Unexpected error %s " % e)
        raise
    finally:
        print("Shutting down IoT Hub Client...")
        loop.run_until_complete(client.shutdown())
        loop.close()


if __name__ == "__main__":
    main()
