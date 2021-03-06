/**
 * Basic Realtime telemetry plugin using websockets.
 */


function TelemetryPlugin() {
    return function (openmct) {
        var ros = new ROSLIB.Ros({
            url: "ws://localhost:9090"
        });
        ros.on('connection', function () {
            console.log('Ros connected');
        });

        ros.on('error', function (error) {
            console.log('Ros connection error', error);
        });

        ros.on('close', function () {
            console.log("Ros connection closed");
        });


        var provider = {
            supportsRequest: function (domainObject) {
                return domainObject.type === 'hopper.telemetry';
            },
            request: function (domainObject, options) {
                return new Promise(function (resolve, reject) {
                    resolve([]);
                });
            },
            supportsSubscribe: function (domainObject) {
                return domainObject.type === 'hopper.telemetry';
            },
            subscribe: function (domainObject, callback) {
                if (domainObject.identifier.key.includes('property.battery')){
                    var hopper_voltage_topic = new ROSLIB.Topic({
                        ros: ros,
                        name: 'hopper/battery_status',
                        messageType: 'sensor_msgs/BatteryState'
                    });
                    console.log("Subscribing to " + domainObject.identifier.key)
                    hopper_voltage_topic.subscribe(function (message) {
                        callback({ "id": "property.battery", "value": message.voltage, "percentage":message.percentage, "timestamp": new Date() });
                    });
                    return function () {
                        hopper_voltage_topic.unsubscribe();
                        console.log("Unsubscribed from hopper");
                    }
                } else if (domainObject.identifier.key === "property.controller.active"){
                    var hopper_face_tracking_on = new ROSLIB.Topic({
                        ros: ros,
                        name: 'hopper/face_tracking_enabled',
                        messageType: 'std_msgs/Bool'
                    });
                    console.log("Subscribing to " + domainObject.identifier.key)
                    hopper_face_tracking_on.subscribe(function (message) {
                        var data = message.data ? "Enabled" : "Disabled";
                        callback({ "id": "property.controller.active", "value": data, "timestamp": new Date() });
                    });
                    return function () {
                        hopper_face_tracking_on.unsubscribe();
                        console.log("Unsubscribed from hopper");
                    }
                }
            }
        };

        openmct.telemetry.addProvider(provider);
    }
}