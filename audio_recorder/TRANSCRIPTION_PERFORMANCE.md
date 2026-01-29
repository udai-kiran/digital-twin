# Transcription Performance Guide

## Issue: "Transcription queue full, dropping audio chunk"

This warning means the Whisper transcription is slower than real-time on your hardware, causing the queue to fill up and audio chunks to be dropped.

## Quick Fixes (Try in Order)

### 1. Use the Tiny Model (Fastest)
```bash
audio-recorder -o output.wav --transcribe --model-size tiny
```
The `tiny` model is 10-20x faster than `base` but slightly less accurate.

### 2. Increase Buffer Size (Less Frequent Transcription)
```bash
audio-recorder -o output.wav --transcribe --buffer-seconds 15
```
Larger buffers mean transcription runs less frequently, giving the model more time to catch up.

### 3. Combine Both
```bash
audio-recorder -o output.wav --transcribe --model-size tiny --buffer-seconds 15
```

## Model Speed Comparison

| Model  | Speed        | Accuracy | Recommended For |
|--------|--------------|----------|-----------------|
| tiny   | 10-20x faster| Good     | **Real-time use, slower hardware** |
| base   | 5-10x faster | Better   | Balanced (default) |
| small  | 2-5x faster  | Best     | Offline processing |
| medium | 1-2x faster  | Excellent| Offline only |
| large  | Slowest      | Best     | Offline only |

## Recent Improvements

I've just made several optimizations to help with this issue:

1. **Increased queue size** - From 100 to 500 items (handles temporary slowdowns)
2. **Optimized Whisper settings**:
   - `beam_size=1` (faster decoding)
   - `condition_on_previous_text=False` (faster, independent segments)
3. **Rate-limited warnings** - Only warns every 5 seconds (reduces log spam)
4. **Better defaults** - Buffer increased from 5s to 10s
5. **Summary statistics** - Shows total dropped chunks at end

## Expected Performance

### On Modern Hardware (2020+ CPU)
- **tiny**: Should work real-time with no drops
- **base**: May drop some chunks under load
- **small**: Will drop chunks, use for offline only

### On Older Hardware (Pre-2020 CPU)
- **tiny**: Should work with occasional drops
- **base**: Will drop many chunks
- **small/medium/large**: Not suitable for real-time

## Understanding the Logs

```
23:16:39 [INFO] Detected language 'te' with probability 0.71
```
✓ This is normal - Whisper auto-detected Telugu language

```
23:16:39 [WARNING] Transcription queue full (dropped 15 chunks).
Consider using a faster model (--model-size tiny) or larger buffer (--buffer-seconds 10)
```
⚠️ This means transcription is falling behind. Follow the suggestions in the message.

```
23:20:45 [WARNING] Total dropped chunks during recording: 127
```
⚠️ Final summary - if this number is high (>100), the transcription is incomplete.

## Trade-offs

### Buffer Size
- **Small (5s)**: More responsive, more frequent updates, higher CPU load
- **Large (15s)**: Less responsive, fewer updates, lower CPU load, better for slow hardware

### Model Size
- **Tiny**: Fast, good accuracy (~90% word accuracy), small model size
- **Base**: Slower, better accuracy (~95% word accuracy), larger model size
- **Larger models**: Much slower, marginal accuracy gains for most use cases

## Recommended Configurations

### For Real-Time Transcription (Live Notes)
```bash
audio-recorder -o output.wav --transcribe --model-size tiny --buffer-seconds 10
```

### For Recording with Transcription (Post-Review)
```bash
audio-recorder -o output.wav --transcribe --model-size base --buffer-seconds 15
```

### For Maximum Accuracy (Offline Processing)
Record first, transcribe later:
```bash
# Step 1: Record without transcription
audio-recorder -o recording.wav --duration 3600

# Step 2: Transcribe offline with large model (future feature)
# (Currently transcription must happen during recording)
```

## CPU Usage

Typical CPU usage per model:
- **tiny**: 20-30% of one core
- **base**: 40-60% of one core
- **small**: 70-90% of one core
- **medium/large**: 100%+ (multi-core)

If you're recording and doing other CPU-intensive tasks, use `tiny`.

## Future Improvements

Potential enhancements to improve performance:
1. **GPU support** - 10-50x speedup with NVIDIA GPU
2. **Batch processing** - Process multiple segments together
3. **Adaptive buffering** - Automatically adjust buffer size based on queue depth
4. **Background mode** - Transcribe after recording completes
5. **Streaming mode** - Incremental transcription with lower latency

## Still Having Issues?

If you're still getting dropped chunks after trying `tiny` model with large buffer:

1. **Check CPU usage**: Run `top` or `htop` while recording
2. **Close other applications**: Free up CPU resources
3. **Use lower sample rate**: Add `--sample-rate 16000` (lower quality but faster)
4. **Record without transcription**: Transcribe the audio file separately later

## Questions?

- Is transcription accurate despite dropped chunks? **Partially - gaps in transcription**
- Do dropped chunks affect the WAV recording? **No - recording is always complete**
- Can I transcribe the WAV file afterwards? **Not currently - future feature**
