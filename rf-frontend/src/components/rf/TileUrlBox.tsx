import React, { useCallback, useState } from 'react';
import { Check, Copy, ExternalLink } from 'lucide-react';
import { STATUS, type C } from '../../design-system/tokens';
import { Button } from './ui';

/* ============================================================================
 * TileUrlBox — the payoff of the whole product.
 *
 * This exact string is what gets pasted into OpenLayers, MapLibre, Leaflet,
 * Cesium or Unreal, so it is shown verbatim (placeholders included) and
 * copied verbatim.
 * ========================================================================== */

interface Props {
  C: C;
  url: string;
  /** Optional concrete tile to open, for a quick "does it really serve?" check. */
  sampleUrl?: string | null;
}

export const TileUrlBox: React.FC<Props> = ({ C, url, sampleUrl }) => {
  const [copied, setCopied] = useState(false);

  const copy = useCallback(async () => {
    try {
      await navigator.clipboard.writeText(url);
    } catch {
      // Clipboard API needs a secure context; fall back to a hidden textarea.
      const ta = document.createElement('textarea');
      ta.value = url;
      ta.style.position = 'fixed';
      ta.style.opacity = '0';
      document.body.appendChild(ta);
      ta.select();
      try {
        document.execCommand('copy');
      } catch {
        /* nothing more we can do; the URL is visible and selectable */
      }
      ta.remove();
    }
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1800);
  }, [url]);

  return (
    <div>
      <div
        style={{
          display: 'flex',
          alignItems: 'stretch',
          gap: 8,
          flexWrap: 'wrap',
        }}
      >
        <code
          style={{
            flex: '1 1 320px',
            minWidth: 0,
            background: C.inp,
            border: `1px solid ${C.inpB}`,
            borderRadius: 7,
            padding: '8px 12px',
            fontSize: 12,
            fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Consolas, monospace',
            color: C.t1,
            wordBreak: 'break-all',
            display: 'flex',
            alignItems: 'center',
          }}
        >
          {url}
        </code>

        <Button
          C={C}
          variant={copied ? 'secondary' : 'primary'}
          icon={copied ? Check : Copy}
          onClick={copy}
        >
          {copied ? 'Copied' : 'Copy URL'}
        </Button>

        {sampleUrl && (
          <Button
            C={C}
            variant="secondary"
            icon={ExternalLink}
            onClick={() => window.open(sampleUrl, '_blank', 'noopener')}
            title="Open a single tile to confirm the endpoint serves"
          >
            Test tile
          </Button>
        )}
      </div>

      {copied && (
        <div style={{ fontSize: 11, color: STATUS.green, marginTop: 8 }}>
          Copied to clipboard.
        </div>
      )}
    </div>
  );
};
