import React from 'react';
import { AlertTriangle, Layers } from 'lucide-react';
import { STATUS, type C } from '../../design-system/tokens';
import type { RasterMetadata } from '../../types/rasterforge';
import {
  formatBytes,
  formatCrs,
  formatDimensions,
  formatGsd,
  formatPixelSize,
} from './format';
import { Card, KeyValue, Notice, PanelTitle, SectionLabel } from './ui';

/* ============================================================================
 * MetadataPanel — what gdalinfo found, in the terms an operator reasons in.
 *
 * The band table is the important part: it is where an Alpha band coexisting
 * with NoData=0 becomes visible, which is the failure this whole product was
 * built to stop happening silently.
 * ========================================================================== */

export const BandTable: React.FC<{ C: C; metadata: RasterMetadata }> = ({ C, metadata }) => {
  const bands = metadata.bands ?? [];
  if (bands.length === 0) {
    return <div style={{ fontSize: 12, color: C.t3 }}>No band information available.</div>;
  }

  const th: React.CSSProperties = {
    textAlign: 'left',
    fontSize: 10,
    fontWeight: 700,
    textTransform: 'uppercase',
    letterSpacing: '0.08em',
    color: C.t3,
    padding: '0 12px 8px 0',
  };
  const td: React.CSSProperties = {
    fontSize: 12,
    color: C.t1,
    padding: '8px 12px 8px 0',
    borderTop: `1px solid ${C.b}`,
  };

  return (
    <div style={{ overflowX: 'auto' }}>
      <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: 380 }}>
        <thead>
          <tr>
            <th style={th}>Band</th>
            <th style={th}>Interpretation</th>
            <th style={th}>Type</th>
            <th style={th}>NoData</th>
          </tr>
        </thead>
        <tbody>
          {bands.map((band) => {
            const risky = band.is_alpha && band.nodata === 0;
            return (
              <tr key={band.index}>
                <td style={{ ...td, fontWeight: 600 }}>{band.index}</td>
                <td style={{ ...td, color: band.is_alpha ? C.accent : C.t1 }}>
                  {band.color_interp}
                  {band.is_alpha && (
                    <span style={{ fontSize: 10, color: C.t3, marginLeft: 6 }}>(alpha)</span>
                  )}
                </td>
                <td style={{ ...td, color: C.t2 }}>{band.dtype}</td>
                <td
                  style={{
                    ...td,
                    color: risky ? STATUS.amber : band.nodata === null ? C.t3 : C.t1,
                    fontWeight: risky ? 600 : 400,
                  }}
                >
                  {band.nodata === null ? '—' : band.nodata}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
};

export const NoDataWarning: React.FC<{ C: C; warning: string }> = ({ C, warning }) => (
  <Notice C={C} tone="warn" title="NoData configuration detected">
    {warning}
    <div style={{ marginTop: 8, color: C.t3 }}>
      With <strong>Auto</strong> handling, RasterForge writes a NoData-stripped working copy
      before tiling and leaves your source file untouched.
    </div>
  </Notice>
);

interface Props {
  C: C;
  metadata: RasterMetadata;
  sourceFilename: string;
  sourceSize: number;
}

export const MetadataPanel: React.FC<Props> = ({ C, metadata, sourceFilename, sourceSize }) => (
  <Card C={C}>
    <PanelTitle C={C} icon={Layers}>
      Raster analysis
    </PanelTitle>

    <div
      style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))',
        gap: 24,
      }}
    >
      <div>
        <SectionLabel C={C}>File</SectionLabel>
        <KeyValue C={C} label="Filename" value={sourceFilename} />
        <KeyValue C={C} label="Size" value={formatBytes(sourceSize)} />
        <KeyValue C={C} label="Driver" value={metadata.driver ?? '—'} />
        <KeyValue C={C} label="Dimensions" value={formatDimensions(metadata.width, metadata.height)} />
      </div>

      <div>
        <SectionLabel C={C}>Spatial</SectionLabel>
        <KeyValue C={C} label="CRS" value={metadata.crs_name ?? '—'} />
        <KeyValue C={C} label="EPSG" value={formatCrs(metadata.epsg, metadata.crs_name)} />
        <KeyValue
          C={C}
          label="Pixel size"
          value={formatPixelSize(metadata.pixel_size_x, metadata.pixel_size_y)}
        />
        <KeyValue C={C} label="Approx. GSD" value={formatGsd(metadata.gsd_m)} />
        {metadata.center && (
          <KeyValue
            C={C}
            label="Center"
            value={`${metadata.center[1].toFixed(6)}, ${metadata.center[0].toFixed(6)}`}
            mono
          />
        )}
        {metadata.bounds && (
          <KeyValue
            C={C}
            label="Bounds"
            value={
              <span style={{ fontSize: 11 }}>
                {metadata.bounds[0].toFixed(5)}, {metadata.bounds[1].toFixed(5)} →{' '}
                {metadata.bounds[2].toFixed(5)}, {metadata.bounds[3].toFixed(5)}
              </span>
            }
            mono
          />
        )}
      </div>
    </div>

    <div style={{ marginTop: 24 }}>
      <SectionLabel C={C}>Bands ({metadata.band_count ?? 0})</SectionLabel>
      <BandTable C={C} metadata={metadata} />
    </div>

    {!metadata.epsg && !metadata.crs_name && (
      <div style={{ marginTop: 16 }}>
        <Notice C={C} tone="error" title="No coordinate reference system">
          <AlertTriangle size={12} style={{ verticalAlign: -2, marginRight: 4 }} />
          This raster has no projection metadata, so it cannot be placed on a web map. Re-export
          it with a CRS before tiling.
        </Notice>
      </div>
    )}

    {metadata.nodata_warning && (
      <div style={{ marginTop: 16 }}>
        <NoDataWarning C={C} warning={metadata.nodata_warning} />
      </div>
    )}
  </Card>
);
