import websockets
import asyncio

async def test_ws():
    async with websockets.connect("ws://ocpp-gateway-2337d11bee44a15c.elb.us-east-2.amazonaws.com:80/ws/ocpp/CP1") as websocket:
        await websocket.send('[2,"316bc795-6b88-4fa0-977a-9ba8347c1962"\
                             ,"BootNotification",{"chargingStation":{"serialNumber":"CP1234567890A01","model":"CHARGE_POINT_MODEL",\
                             "vendorName":"CHARGE_POINT_VENDOR","firmwareVersion":"1.2.3.4",\
                             "modem":{"iccid":"891004234814455936F","imsi":"310410123456789"}},\
                             "reason":"PowerUp"}];')
        response = await websocket.recv()
        print(f"Response: {response}")

asyncio.run(test_ws())
