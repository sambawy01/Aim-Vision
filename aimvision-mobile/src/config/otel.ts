/**
 * OpenTelemetry placeholder. Real wiring lands in Sprint 6 per
 * docs/observability-plan.md and docs/mobile-architecture.md §13.
 */
import { env } from './env';

export interface OtelSpan {
  name: string;
  attributes?: Record<string, string | number | boolean>;
  end: () => void;
}

export function initOtel(): void {
  if (!env.otelEndpoint) return;
  // Sprint 6: initialize @opentelemetry/sdk-node-equivalent for RN, OTLP exporter,
  // resource attrs (service.name=aimvision-mobile, device.tier, app.version).
}

export function startSpan(name: string, attributes?: OtelSpan['attributes']): OtelSpan {
  return {
    name,
    attributes,
    end: () => undefined,
  };
}
