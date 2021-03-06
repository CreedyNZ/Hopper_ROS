﻿var socket = createSocketIOConnection();

const telemetryVm = new Vue({
    el: '#telemetry_display',
    data: {
        averageTemperature: 0,
        averageVoltage: 0,
        connected: false,
        liftHeight: 3
    },
    watch: {
        connected: function () {
            console.log("Connection status changed to " + this.connected);
        },
        liftHeight: function() {
            socket.emit('walkingModeUpdate', {
                liftHeight: this.liftHeight
            });
        }
    }
});

setInterval(function () {
    telemetryVm.connected = socket.connected;
}, 250);

socket.on('telemetry', function (msg) {
    const voltageSum = msg.servos.reduce(function (acum, servo) { return acum + servo.voltage; }, 0);
    const temperatureSum = msg.servos.reduce(function (acum, servo) { return acum + servo.temperature; }, 0);
    const averageVoltage = voltageSum / msg.servos.length;
    const averageTemperature = temperatureSum / msg.servos.length;
    telemetryVm.averageVoltage = averageVoltage;
    telemetryVm.averageTemperature = averageTemperature;
});

const movementJoystick = createJoystick({
    elementId: "#move_joystick_zone",
    color: "red",
    name: "direction",
    socket: socket
});

const rotationJoystick = createJoystick({
    elementId: "#rotate_joystick_zone",
    color: "navy",
    name: "rotation",
    socket: socket
});

setGamepadWatchdog(socket, 0);
