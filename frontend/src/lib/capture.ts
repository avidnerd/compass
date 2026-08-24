export async function captureVideoFrame({
  video,
  maxWidth = 1280,
  quality = 0.65,
}: {
  video: HTMLVideoElement
  maxWidth?: number
  quality?: number
}): Promise<{ blob: Blob; width: number; height: number }> {
  if (!video.videoWidth || !video.videoHeight) {
    throw new Error('The shared screen is not ready yet.')
  }
  const scale = Math.min(1, maxWidth / video.videoWidth)
  const width = Math.round(video.videoWidth * scale)
  const height = Math.round(video.videoHeight * scale)
  const canvas = document.createElement('canvas')
  canvas.width = width
  canvas.height = height
  const context = canvas.getContext('2d')
  if (!context) throw new Error('Unable to prepare a private screen sample.')
  context.drawImage(video, 0, 0, width, height)
  const blob = await new Promise<Blob>((resolve, reject) => {
    canvas.toBlob((result) => {
      if (result) resolve(result)
      else reject(new Error('Unable to encode a private screen sample.'))
    }, 'image/jpeg', quality)
  })
  return { blob, width, height }
}
