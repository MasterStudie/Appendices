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
import schedule
import threading
import time
import os
from datetime import datetime, timezone, timedelta
import json
#------------------------------------------------------------------------------
#------------------------------------------------------------------------------
#Added by thesis author, based on work by:
#Code author: Daniel Bader
#Code source: https://schedule.readthedocs.io/en/stable/background-execution.html
def run_continuously(interval=1):
    """Continuously run, while executing pending jobs at each
    elapsed time interval.
    @return cease_continuous_run: threading. Event which can
    be set to cease continuous run. Please note that it is
    *intended behavior that run_continuously() does not run
    missed jobs*. For example, if you've registered a job that
    should run every minute and you set a continuous run
    interval of one hour then your job won't be run 60 times
    at each interval but only once.
    """
    cease_continuous_run = threading.Event()

    class ScheduleThread(threading.Thread):
        @classmethod
        def run(cls):
            while not cease_continuous_run.is_set():
                schedule.run_pending()
                time.sleep(interval)

    continuous_thread = ScheduleThread()
    continuous_thread.start()
    return cease_continuous_run
#------------------------------------------------------------------------------

# Event indicating client stop
stop_event = threading.Event()


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

#------------------------------------------------------------------------------
#Added by thesis author, based on work by:
#Code author: Daniel Bader
#Code source: https://schedule.readthedocs.io/en/stable/background-execution.html
    def background_job():
        sensor_id = "test"
        start_time = datetime.now(timezone.utc)-timedelta(seconds=1)
        end_time = datetime.now(timezone.utc)
        payload = json.dumps({
            'sensor_id': sensor_id,
            'start_time': datetime.isoformat(start_time),
            'end_time': datetime.isoformat(end_time)
        })
        method_params={
            'methodName': "GetDataSlice",
            'payload': payload,
            'connectTimeoutInSeconds':1,
            'responseTimeoutInSeconds':50
        }
        device_id = 0
        module_id = None
        asyncio.run_coroutine_threadsafe(client.invoke_method(method_params, os.environ["IOTEDGE_DEVICEID"], "LoggingController"), loop)


    schedule.every(45).seconds.do(background_job)

    # Start the background thread
    stop_run_continuously = run_continuously()
#------------------------------------------------------------------------------

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
        # Stop the background thread
        stop_run_continuously.set()


if __name__ == "__main__":
    main()
