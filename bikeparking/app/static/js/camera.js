// camera.js — Handles webcam + WebSocket detection updates

document.addEventListener("DOMContentLoaded", function () {
    const video = document.getElementById("camera");
    const totalSlots = document.getElementById("totalSlots");
    const availableSlots = document.getElementById("availableSlots");
    const occupiedSlots = document.getElementById("occupiedSlots");
    const detectedList = document.getElementById("detectedList");

    // 1️⃣ Initialize webcam
    navigator.mediaDevices.getUserMedia({ video: true })
        .then((stream) => {
            video.srcObject = stream;
        })
        .catch((err) => {
            console.error("Camera access error:", err);
            alert("Unable to access camera. Please allow webcam permissions.");
        });

    // 2️⃣ Connect to WebSocket
    const socket = new WebSocket("ws://" + window.location.host + "/ws/parking/");

    socket.onopen = function () {
        console.log("✅ Connected to WebSocket server");
    };

    socket.onmessage = function (event) {
        const data = JSON.parse(event.data);

        if (data.message) {
            console.log(data.message);
            return;
        }

        totalSlots.innerText = data.total_slots || 0;
        availableSlots.innerText = data.available_slots || 0;
        occupiedSlots.innerText = data.occupied_slots || 0;

        // Clear and re-render detected list
        detectedList.innerHTML = "";
        if (data.detected && data.detected.length > 0) {
            data.detected.forEach(slot => {
                const li = document.createElement("li");
                li.textContent = `Slot ${slot}`;
                detectedList.appendChild(li);
            });
        }
    };

    socket.onclose = function () {
        console.warn("⚠️ WebSocket closed. Retrying in 5 seconds...");
        setTimeout(() => window.location.reload(), 5000);
    };

    socket.onerror = function (err) {
        console.error("WebSocket error:", err);
    };
});
