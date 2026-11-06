export class RequestBodyTooLargeError extends Error {
  constructor(maxBytes: number) {
    super(`Request body exceeds the ${maxBytes}-byte limit`)
    this.name = 'RequestBodyTooLargeError'
  }
}

function declaredLength(request: Request): number | null {
  const value = request.headers.get('content-length')
  if (!value || !/^[0-9]+$/.test(value)) {
    return null
  }
  const length = Number(value)
  return Number.isSafeInteger(length) ? length : null
}

export async function readRequestBody(
  request: Request,
  maxBytes: number
): Promise<ArrayBuffer> {
  if (!Number.isSafeInteger(maxBytes) || maxBytes < 0) {
    throw new RangeError('maxBytes must be a non-negative safe integer')
  }

  const contentLength = declaredLength(request)
  if (contentLength !== null && contentLength > maxBytes) {
    throw new RequestBodyTooLargeError(maxBytes)
  }

  const reader = request.body?.getReader()
  if (!reader) {
    return new ArrayBuffer(0)
  }

  const chunks: Uint8Array[] = []
  let totalBytes = 0
  while (true) {
    const { done, value } = await reader.read()
    if (done) {
      break
    }
    if (!value?.byteLength) {
      continue
    }
    totalBytes += value.byteLength
    if (totalBytes > maxBytes) {
      try {
        await reader.cancel('request body limit exceeded')
      } catch {
        // The size decision is authoritative even if the producer cannot cancel.
      }
      throw new RequestBodyTooLargeError(maxBytes)
    }
    chunks.push(value)
  }

  const body = new Uint8Array(totalBytes)
  let offset = 0
  for (const chunk of chunks) {
    body.set(chunk, offset)
    offset += chunk.byteLength
  }
  return body.buffer
}

export async function readJsonRequestBody(
  request: Request,
  maxBytes: number
): Promise<unknown> {
  const body = await readRequestBody(request, maxBytes)
  if (body.byteLength === 0) {
    throw new SyntaxError('JSON body is empty')
  }
  const text = new TextDecoder('utf-8', { fatal: true }).decode(body)
  return JSON.parse(text) as unknown
}
