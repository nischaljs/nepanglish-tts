async def _frame_loop(self):
    frame_count = 0
    while self.running:
        try:
            data = self.capture.frames.get(timeout=0.2)
        except queue.Empty:
            continue

        frame_count += 1

        if self.streaming:
            self._send_queue.put(data)
            if frame_count % 150 == 0:
                dur = frame_count * 20 / 1000
                log.info("[STREAM] ~%d frames sent (%.1fs)", frame_count, dur)
        else:
            energy = EnergyWakeDetector._rms_energy(data)
            if frame_count % 50 == 0:
                log.info("[KWS] energy=%.0f  threshold=%.0f", energy, self.detector.threshold)

            if self.detector.process_frame(data):
                log.info("[KWS] ⚡ WAKE DETECTED — energy=%.0f  streak=%d frames  prebuf=%d",
                         energy, self.detector.confirm_frames, len(self.detector.pre_buffer))
                for buf in self.detector.pre_buffer:
                    self._send_queue.put(buf)
                self.streaming = True

async def _sender_loop(self):
    bytes_sent = 0
    while self.running:
        try:
            data = self._send_queue.get(timeout=0.05)
            bytes_sent += len(data)
            await self.client.send_audio(data)
            if bytes_sent % 48000 == 0:
                log.info("[STREAM] %.1f KB sent to server", bytes_sent / 1024)
        except queue.Empty:
            await asyncio.sleep(0.01)