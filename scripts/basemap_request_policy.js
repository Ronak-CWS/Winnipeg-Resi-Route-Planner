/* All MapLibre network resources use this one bounded, cached request queue. */
(function (root) {
  'use strict';
  const DEFAULTS = Object.freeze({
    concurrency: 4, maxRequests: 200, maxBytes: 25 * 1024 * 1024,
    minStartIntervalMs: 200, timeoutMs: 12000,
    allowedOrigin: 'https://tiles.openfreemap.org',
  });
  class BasemapRequestPolicy {
    constructor(options = {}) {
      this.options = Object.freeze({...DEFAULTS, ...options});
      this.fetch = options.fetch || root.fetch.bind(root);
      this.onStop = options.onStop || (() => {});
      this.queue = [];
      this.resources = new Map();
      this.controllers = new Set();
      this.active = 0;
      this.peakActive = 0;
      this.started = 0;
      this.bytes = 0;
      this.cacheHits = 0;
      this.lastStart = 0;
      this.stopped = '';
      this.timer = null;
    }
    snapshot() {
      return {started: this.started, bytes: this.bytes, active: this.active,
        peakActive: this.peakActive, queued: this.queue.length, cacheHits: this.cacheHits,
        stopped: this.stopped, maxRequests: this.options.maxRequests,
        maxBytes: this.options.maxBytes, concurrency: this.options.concurrency};
    }
    stop(reason) {
      if (this.stopped) return;
      this.stopped = reason;
      clearTimeout(this.timer);
      this.timer = null;
      for (const job of this.queue.splice(0)) job.reject(new Error(reason));
      for (const controller of this.controllers) controller.abort();
      this.onStop(reason);
    }
    getBytes(url) {
      if (this.resources.has(url)) {
        this.cacheHits++;
        return this.resources.get(url);
      }
      if (this.stopped) return Promise.reject(new Error(this.stopped));
      let parsed;
      try { parsed = new URL(url); } catch { return Promise.reject(new Error('Invalid basemap URL')); }
      if (parsed.origin !== this.options.allowedOrigin) {
        this.stop('An unapproved basemap host was blocked.');
        return Promise.reject(new Error(this.stopped));
      }
      // Count both started and queued unique URLs before accepting more work.
      if (this.started + this.queue.length >= this.options.maxRequests) {
        this.stop('The basemap request limit for this page has been reached.');
        return Promise.reject(new Error(this.stopped));
      }
      const promise = new Promise((resolve, reject) => {
        this.queue.push({url, resolve, reject});
      });
      // Keep failures too: requesting the same failed URL never retries it.
      this.resources.set(url, promise);
      this.pump();
      return promise;
    }
    pump() {
      if (this.stopped || this.timer || this.active >= this.options.concurrency || !this.queue.length) return;
      const wait = Math.max(0, this.lastStart + this.options.minStartIntervalMs - Date.now());
      if (wait) {
        this.timer = setTimeout(() => { this.timer = null; this.pump(); }, wait);
        return;
      }
      const job = this.queue.shift();
      this.active++;
      this.peakActive = Math.max(this.peakActive, this.active);
      this.started++;
      this.lastStart = Date.now();
      this.perform(job).then(job.resolve, job.reject).finally(() => {
        this.active--;
        this.pump();
      });
      this.pump();
    }
    async perform(job) {
      const controller = new AbortController();
      this.controllers.add(controller);
      const timer = setTimeout(() => {
        this.stop('The basemap request timed out; automatic loading has stopped.');
      }, this.options.timeoutMs);
      try {
        const response = await this.fetch(job.url, {signal: controller.signal, cache: 'default', credentials: 'omit'});
        if (!response.ok) throw new Error(`Basemap HTTP ${response.status}; automatic loading has stopped.`);
        const chunks = [];
        let size = 0;
        if (response.body && response.body.getReader) {
          const reader = response.body.getReader();
          for (;;) {
            const {value, done} = await reader.read();
            if (done) break;
            size += value.byteLength;
            this.bytes += value.byteLength;
            if (this.bytes > this.options.maxBytes) throw new Error('The basemap transfer limit for this page has been reached.');
            chunks.push(value);
          }
        } else {
          const value = new Uint8Array(await response.arrayBuffer());
          size = value.byteLength;
          this.bytes += size;
          if (this.bytes > this.options.maxBytes) throw new Error('The basemap transfer limit for this page has been reached.');
          chunks.push(value);
        }
        const data = new Uint8Array(size);
        let offset = 0;
        for (const chunk of chunks) { data.set(chunk, offset); offset += chunk.byteLength; }
        return {buffer: data.buffer, cacheControl: response.headers.get('Cache-Control') || 'max-age=86400'};
      } catch (error) {
        this.stop(error.message || 'Basemap loading failed; automatic loading has stopped.');
        throw error;
      } finally {
        clearTimeout(timer);
        this.controllers.delete(controller);
      }
    }
    async request(parameters, abortController) {
      const signal = abortController && abortController.signal;
      if (signal && signal.aborted) throw new DOMException('Aborted', 'AbortError');
      const url = decodeURIComponent(parameters.url.replace(/^cws-ofm:\/\//, ''));
      const result = await this.getBytes(url);
      if (signal && signal.aborted) throw new DOMException('Aborted', 'AbortError');
      let data;
      if (parameters.type === 'json') data = JSON.parse(new TextDecoder().decode(result.buffer));
      else if (parameters.type === 'string') data = new TextDecoder().decode(result.buffer);
      // Workers may transfer ownership; retain an independent cached buffer.
      else data = result.buffer.slice(0);
      return {data, cacheControl: result.cacheControl};
    }
  }
  root.CwsBasemapRequestPolicy = BasemapRequestPolicy;
  root.CwsBasemapRequestDefaults = DEFAULTS;
})(globalThis);
