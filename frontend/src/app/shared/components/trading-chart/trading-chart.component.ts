/**
 * TradingView Chart Component
 * 
 * Renders candlestick charts with annotations using TradingView Charting Library
 */

import { Component, Input, OnInit, OnDestroy, AfterViewInit, ElementRef, ViewChild, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { HttpClient } from '@angular/common/http';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatIconModule } from '@angular/material/icon';
import { environment } from '../../../../environments/environment';

export interface ChartData {
  meta?: {
    symbol: string;
    timeframe: string;
    generated_at?: string;
    candle_count?: number;
  };
  symbol?: string; // Fallback for direct symbol
  timeframe?: string; // Fallback for direct timeframe
  candles: Array<{
    time?: string | number; // Backend uses "time"
    timestamp?: string | number; // Alternative field name
    open: number;
    high: number;
    low: number;
    close: number;
    volume: number;
  }>;
  annotations?: {
    shapes?: any[];
    markers?: any[];
    lines?: any[];
    arrows?: any[];
    zones?: any[];
    text?: any[];
    position?: {
      action: string;
      entry_price: number;
      stop_loss?: number;
      take_profit?: number;
      confidence?: number;
      pattern?: string;
      risk?: number;
      reward?: number;
      rr_ratio?: number;
      position_size?: number;
    };
  };
  indicators?: {
    rsi?: any;
    macd?: any;
  };
  decision?: {
    action?: string;
    entry_price?: number;
    stop_loss?: number;
    take_profit?: number;
    confidence?: number;
    pattern?: string;
    position_size?: number;
  };
  metadata?: {
    strategy?: string;
    action?: string;
    confidence?: number;
    generated_at?: string;
  };
}

@Component({
  selector: 'app-trading-chart',
  standalone: true,
  imports: [CommonModule, MatProgressSpinnerModule, MatIconModule],
  templateUrl: './trading-chart.component.html',
  styleUrls: ['./trading-chart.component.scss']
})
export class TradingChartComponent implements OnInit, AfterViewInit, OnDestroy {
  @Input() chartData!: ChartData;
  @Input() height: number = 500;
  /** Trade execution context — provides actual execution/fill timestamps for position tool alignment */
  @Input() tradeContext?: {
    execution_time?: string;  // When order was queued/placed
    filled_price?: number;
    filled_quantity?: number;
    closed_at?: string;       // When position was closed
  };
  @ViewChild('chartContainer') chartContainer!: ElementRef;

  private http = inject(HttpClient);
  private widget: any;
  private currentInterval: string = 'D';
  private createdShapes: any[] = [];
  /** Candles to render — fresh from data plane when available, else stored in chartData */
  private resolvedCandles: any[] = [];
  loading = true;
  error: string | null = null;
  infoPanelEntries: { text: string; color: string; bold?: boolean }[] = [];

  ngOnInit(): void {
    if (!this.chartData) {
      this.error = 'No chart data provided';
      this.loading = false;
    }
  }

  ngAfterViewInit(): void {
    if (this.chartData && this.chartData.candles && this.chartData.candles.length > 0) {
      // Try to fetch fresh candles from data plane (covers full trade lifecycle)
      this.fetchFreshCandles().then(fresh => {
        this.resolvedCandles = fresh || this.chartData.candles;
        console.log('Chart rendering with', this.resolvedCandles.length, 'candles',
          fresh ? '(fresh from data plane)' : '(stored in execution)');
        this.loadTradingViewLibrary();
      });
    } else {
      this.error = 'Invalid or empty chart data';
      this.loading = false;
      console.error('Invalid chart data:', this.chartData);
    }
  }

  /** Fetch fresh candles from data plane and merge with stored candles for full trade lifecycle */
  private async fetchFreshCandles(): Promise<any[] | null> {
    const symbol = this.chartData.meta?.symbol || this.chartData.symbol;
    const timeframe = this.chartData.meta?.timeframe || this.chartData.timeframe || '5m';
    if (!symbol) return null;

    try {
      const url = `${environment.apiUrl}/api/v1/executions/candles/${symbol}?timeframe=${timeframe}&limit=500`;
      const data: any = await this.http.get(url).toPromise();
      const freshCandles = data?.candles;
      if (!freshCandles || freshCandles.length === 0) return null;

      // Merge stored + fresh candles, deduplicate by timestamp
      const stored = this.chartData.candles || [];
      const allCandles = [...stored, ...freshCandles];
      const seen = new Set<string>();
      const merged = allCandles.filter(c => {
        const key = String(c.time || c.timestamp);
        if (seen.has(key)) return false;
        seen.add(key);
        return true;
      });
      merged.sort((a, b) => {
        const ta = new Date(a.time || a.timestamp).getTime();
        const tb = new Date(b.time || b.timestamp).getTime();
        return ta - tb;
      });
      console.log(`Candle merge: ${stored.length} stored + ${freshCandles.length} fresh → ${merged.length} merged`);
      return merged;
    } catch (err) {
      console.warn('Could not fetch fresh candles, using stored data:', err);
      return null;
    }
  }

  ngOnDestroy(): void {
    this.createdShapes.forEach(shape => {
      try { shape.remove(); } catch (_) {}
    });
    this.createdShapes = [];
    if (this.widget) {
      this.widget.remove();
    }
  }

  private loadTradingViewLibrary(): void {
    // Check if TradingView library is already loaded
    if ((window as any).TradingView) {
      this.initializeChart();
    } else {
      // Load TradingView library
      const script = document.createElement('script');
      script.src = '/libs/charting_library-master/charting_library/charting_library.standalone.js';
      script.async = true;
      script.onload = () => this.initializeChart();
      script.onerror = () => {
        this.error = 'Failed to load TradingView library';
        this.loading = false;
      };
      document.head.appendChild(script);
    }
  }

  private initializeChart(): void {
    try {
      // Get symbol and timeframe with fallbacks
      const symbol = this.chartData.meta?.symbol || this.chartData.symbol || 'UNKNOWN';
      const timeframe = this.chartData.meta?.timeframe || this.chartData.timeframe || '5m';

      // Validate chart data
      if (!symbol || symbol === 'UNKNOWN' || !this.resolvedCandles || this.resolvedCandles.length === 0) {
        this.error = 'Invalid chart data: missing symbol or candles';
        this.loading = false;
        console.error('Chart data validation failed:', { symbol, candlesCount: this.resolvedCandles?.length });
        return;
      }

      // Lock to the data's timeframe — we only have candles for this resolution
      this.currentInterval = this.timeframeToInterval(timeframe);

      const datafeed = this.createDatafeed();
      
      this.widget = new (window as any).TradingView.widget({
        container: this.chartContainer.nativeElement,
        datafeed: datafeed,
        symbol: symbol,
        interval: this.timeframeToInterval(timeframe),
        library_path: '/libs/charting_library-master/charting_library/',
        locale: 'en',
        timezone: Intl.DateTimeFormat().resolvedOptions().timeZone as any,
        disabled_features: [
          'use_localstorage_for_settings',
          'volume_force_overlay',
          'header_symbol_search',
          'symbol_search_hot_key',
          'create_volume_indicator_by_default',
          'popup_hints',
        ],
        enabled_features: ['study_templates'],
        charts_storage_api_version: '1.1',
        client_id: 'trading-platform',
        user_id: 'public',
        fullscreen: false,
        autosize: true,
        theme: 'light',
        overrides: {
          'mainSeriesProperties.candleStyle.upColor': '#26a69a',
          'mainSeriesProperties.candleStyle.downColor': '#ef5350',
          'mainSeriesProperties.candleStyle.borderUpColor': '#26a69a',
          'mainSeriesProperties.candleStyle.borderDownColor': '#ef5350',
          'mainSeriesProperties.candleStyle.wickUpColor': '#26a69a',
          'mainSeriesProperties.candleStyle.wickDownColor': '#ef5350',
          'paneProperties.background': '#ffffff',
          'paneProperties.vertGridProperties.color': '#f0f0f0',
          'paneProperties.horzGridProperties.color': '#f0f0f0',
        },
        studies_overrides: {
          'volume.volume.color.0': '#ef5350',
          'volume.volume.color.1': '#26a69a',
          'volume.volume.transparency': 50,
        },
      });

      this.widget.onChartReady(() => {
        this.addAnnotations();
        this.loading = false;
      });

    } catch (error) {
      console.error('Error initializing chart:', error);
      this.error = 'Failed to initialize chart: ' + (error as Error).message;
      this.loading = false;
    }
  }

  private createDatafeed(): any {
    const candles = this.resolvedCandles;
    let isFirstCall = true; // Track first call to prevent infinite loops
    
    return {
      onReady: (callback: any) => {
        setTimeout(() => callback({
          supported_resolutions: [this.currentInterval],
          supports_marks: false,
          supports_timescale_marks: false,
          supports_time: true,
        }), 0);
      },
      
      resolveSymbol: (symbolName: string, onSymbolResolvedCallback: any, onResolveErrorCallback: any) => {
        const symbolInfo = {
          name: symbolName,
          description: '',
          type: 'stock',
          session: '24x7',
          timezone: Intl.DateTimeFormat().resolvedOptions().timeZone as any,
          ticker: symbolName,
          exchange: '',
          minmov: 1,
          pricescale: 100,
          has_intraday: true,
          has_no_volume: false,
          has_weekly_and_monthly: false,
          supported_resolutions: [this.currentInterval],
          volume_precision: 2,
          data_status: 'endofday',
        };
        setTimeout(() => onSymbolResolvedCallback(symbolInfo), 0);
      },

      getBars: (symbolInfo: any, resolution: string, periodParams: any, onHistoryCallback: any, onErrorCallback: any) => {
        try {
          // Only return data on first call, then indicate no more data
          if (!isFirstCall) {
            console.log('getBars: No more historical data');
            onHistoryCallback([], { noData: true });
            return;
          }

          isFirstCall = false;

          const bars = candles
            .map(candle => {
              // Get timestamp - backend uses "time" field, but check both
              const rawTime = candle.time || candle.timestamp;
              
              if (!rawTime) {
                console.warn('Candle missing time field:', candle);
                return null;
              }

              // Parse timestamp - handle both ISO string and Unix timestamp
              let timestamp: number;
              if (typeof rawTime === 'number') {
                // If it's already a number, assume it's milliseconds
                timestamp = rawTime;
              } else {
                // Parse as date string
                const date = new Date(rawTime);
                timestamp = date.getTime();
              }

              // Validate timestamp
              if (isNaN(timestamp) || timestamp <= 0) {
                console.warn('Invalid timestamp:', rawTime, 'for candle:', candle);
                return null;
              }

              return {
                time: timestamp,
                open: Number(candle.open),
                high: Number(candle.high),
                low: Number(candle.low),
                close: Number(candle.close),
                volume: Number(candle.volume || 0),
              };
            })
            .filter(bar => bar !== null) as any[]; // Remove invalid bars

          if (bars.length === 0) {
            console.error('No valid candle data after filtering. Sample candle:', candles[0]);
            onHistoryCallback([], { noData: true });
            return;
          }

          // Sort bars by time (oldest first)
          bars.sort((a, b) => a.time - b.time);

          console.log('getBars: Loaded bars:', bars.length, 'First:', new Date(bars[0].time), 'Last:', new Date(bars[bars.length - 1].time));
          
          // Return all bars and indicate no more data available
          onHistoryCallback(bars, { noData: false });
        } catch (error) {
          console.error('Error getting bars:', error);
          onErrorCallback('Failed to load chart data: ' + (error as Error).message);
        }
      },

      subscribeBars: () => {
        // No real-time updates
      },
      
      unsubscribeBars: () => {
        // No real-time updates
      },
    };
  }

  private getLabelText(label: any): string {
    if (!label) return '';
    if (typeof label === 'string') return label;
    if (typeof label === 'object' && label.text) return label.text;
    return String(label);
  }

  private addAnnotations(): void {
    if (!this.chartData.annotations || !this.widget) {
      return;
    }

    try {
      const chart = this.widget.activeChart();
      const candles = this.resolvedCandles || this.chartData.candles || [];

      if (candles.length === 0) {
        console.warn('No candles available for annotations');
        return;
      }

      const firstTime = new Date(candles[0].time || candles[0].timestamp || Date.now()).getTime() / 1000;
      const lastTime = new Date(candles[candles.length - 1].time || candles[candles.length - 1].timestamp || Date.now()).getTime() / 1000;
      const annotations = this.chartData.annotations;

      // Resolve position: prefer annotations.position, fall back to decision
      const position = annotations.position || this.buildPositionFromDecision();
      const hasPosition = !!(position && position.entry_price && position.action && position.action !== 'HOLD');

      // 1. Zones (premium/discount background shading)
      this.addZoneAnnotations(chart, annotations.zones || [], firstTime, lastTime);

      // 2. Shapes (FVG rectangles)
      this.addShapeAnnotations(chart, annotations.shapes || [], firstTime, lastTime);

      // 3. Lines (liquidity levels — skip SL/TP if position exists)
      this.addLineAnnotations(chart, annotations.lines || [], firstTime, lastTime, hasPosition);

      // 4. Position (entry + SL + TP using TradingView position tool)
      if (hasPosition) {
        const candleInterval = candles.length > 1
          ? (lastTime - firstTime) / (candles.length - 1)
          : 300;
        // Find entry/exit times for position annotations
        const entryTime = this.findEntryTime(annotations.markers || [], lastTime);
        const exitTime = this.findExitTime(annotations.markers || [], lastTime);
        this.addPositionAnnotations(chart, position!, entryTime, candleInterval, exitTime);
      }

      // 5. Markers (swing highs/lows, execution marks)
      this.addMarkerAnnotations(chart, annotations.markers || [], lastTime);

      // 6. Arrows (BOS/CHoCH)
      this.addArrowAnnotations(chart, annotations.arrows || [], lastTime);

      // 7. Info panel (consolidated text labels)
      this.addTextAnnotations(chart, annotations.text || [], candles, firstTime, lastTime, position);

      // 8. Indicator studies (RSI, MACD)
      this.addIndicatorStudies(chart);

      console.log('Annotations added successfully');

    } catch (error) {
      console.error('Error adding annotations:', error);
    }
  }

  private addZoneAnnotations(chart: any, zones: any[], firstTime: number, lastTime: number): void {
    zones.forEach((zone: any) => {
      try {
        const shape = chart.createMultipointShape([
          { time: firstTime, price: zone.price1 },
          { time: lastTime, price: zone.price2 }
        ], {
          shape: 'rectangle',
          lock: true,
          disableSelection: true,
          disableSave: true,
          zOrder: 'bottom',
          overrides: {
            backgroundColor: zone.color || 'rgba(0, 0, 0, 0.1)',
            borderColor: 'transparent',
            borderWidth: 0,
            transparency: 85,
          },
        });
        if (shape) this.createdShapes.push(shape);
      } catch (err) {
        console.warn('Failed to add zone:', err);
      }
    });
  }

  private addShapeAnnotations(chart: any, shapes: any[], firstTime: number, lastTime: number): void {
    shapes.forEach((shape: any) => {
      try {
        if (shape.price1 && shape.price2 && !shape.points) {
          const shapeStartTime = shape.time1
            ? new Date(shape.time1).getTime() / 1000
            : firstTime;
          const s = chart.createMultipointShape([
            { time: shapeStartTime, price: shape.price1 },
            { time: lastTime, price: shape.price2 }
          ], {
            shape: shape.type || 'rectangle',
            lock: true,
            disableSelection: true,
            disableSave: true,
            zOrder: 'bottom',
            overrides: {
              backgroundColor: shape.color || 'rgba(0, 0, 0, 0.1)',
              borderColor: shape.border_color || shape.color || '#000',
              borderWidth: shape.border_width || 1,
              transparency: Math.round((1 - (shape.opacity || 0.2)) * 100),
            },
          });
          if (s) this.createdShapes.push(s);

          // Add FVG/shape label text at the left edge
          if (shape.label) {
            const labelText = this.getLabelText(shape.label);
            const midPrice = (shape.price1 + shape.price2) / 2;
            const tl = chart.createMultipointShape([{ time: shapeStartTime, price: midPrice }], {
              shape: 'text',
              lock: true,
              disableSelection: true,
              disableSave: true,
              overrides: {
                color: shape.label?.color || shape.color || '#000',
                fontsize: shape.label?.font_size || 10,
                bold: false,
                text: labelText,
              },
            });
            if (tl) this.createdShapes.push(tl);
          }
        } else if (shape.points) {
          const s = chart.createMultipointShape(shape.points, {
            shape: shape.type || 'rectangle',
            lock: true,
            disableSelection: true,
            disableSave: true,
            zOrder: 'bottom',
            overrides: shape.style || {},
          });
          if (s) this.createdShapes.push(s);
        }
      } catch (err) {
        console.warn('Failed to add shape:', err);
      }
    });
  }

  private addLineAnnotations(chart: any, lines: any[], firstTime: number, lastTime: number, skipTradeLines: boolean): void {
    lines.forEach((line: any) => {
      try {
        if (line.type === 'horizontal' && line.price) {
          // Skip SL/TP/Fill lines when position tool handles them
          if (skipTradeLines) {
            const labelText = this.getLabelText(line.label).toUpperCase();
            if (labelText.includes('SL:') || labelText.includes('TP:') || labelText.includes('ENTRY') || labelText.includes('FILL')) {
              return;
            }
          }
          const s = chart.createMultipointShape([
            { time: firstTime, price: line.price },
            { time: lastTime, price: line.price }
          ], {
            shape: 'trend_line',
            lock: true,
            disableSelection: true,
            disableSave: true,
            overrides: {
              linecolor: line.color || '#000',
              linewidth: line.width || 1,
              linestyle: line.style === 'dashed' ? 2 : line.style === 'dotted' ? 1 : 0,
              showLabel: true,
              textcolor: line.color || '#000',
            },
          });
          if (s) this.createdShapes.push(s);
        }
      } catch (err) {
        console.warn('Failed to add line:', err);
      }
    });
  }

  /** Parse a timestamp string as UTC (backend timestamps have no 'Z' suffix) */
  private parseUtcTime(raw: string | number): number {
    if (typeof raw === 'number') return raw;
    let s = raw;
    // Append 'Z' if no timezone indicator so JS parses as UTC, not local time
    if (s && !s.endsWith('Z') && !s.includes('+') && !s.includes('-', 10)) {
      s += 'Z';
    }
    return new Date(s).getTime() / 1000;
  }

  /** Find entry timestamp: tradeContext.execution_time > ENTRY marker > last candle */
  private findEntryTime(markers: any[], lastTime: number): number {
    // 1. Trade execution time (when trade manager queued the order)
    if (this.tradeContext?.execution_time) {
      const t = this.parseUtcTime(this.tradeContext.execution_time);
      if (!isNaN(t) && t > 0) return t;
    }

    // 2. ENTRY marker timestamp from annotations
    for (const m of markers) {
      const text = (m.text || m.label || '').toUpperCase();
      if (text === 'ENTRY' || text.includes('ENTRY')) {
        const rawTime = m.timestamp || m.time;
        if (rawTime) {
          const t = this.parseUtcTime(rawTime);
          if (!isNaN(t) && t > 0) return t;
        }
      }
    }

    // 3. Fall back to last candle (when strategy made its decision)
    return lastTime;
  }

  /** Find exit timestamp: tradeContext.closed_at > EXIT marker > last candle */
  private findExitTime(markers: any[], lastTime: number): number {
    // 1. Trade close time from context
    if (this.tradeContext?.closed_at) {
      const t = this.parseUtcTime(this.tradeContext.closed_at);
      if (!isNaN(t) && t > 0) return t;
    }

    // 2. EXIT marker timestamp
    for (const m of markers) {
      const text = (m.text || m.label || '').toUpperCase();
      if (text.includes('EXIT')) {
        const rawTime = m.timestamp || m.time;
        if (rawTime) {
          const t = this.parseUtcTime(rawTime);
          if (!isNaN(t) && t > 0) return t;
        }
      }
    }
    return lastTime;
  }

  /** Build position data from chartData.decision when annotations.position is missing */
  private buildPositionFromDecision(): any | null {
    const d = this.chartData?.decision;
    if (!d || !d.action || !d.entry_price) return null;
    return {
      action: d.action,
      entry_price: d.entry_price,
      stop_loss: d.stop_loss,
      take_profit: d.take_profit,
      confidence: d.confidence,
      pattern: d.pattern,
      position_size: d.position_size,
    };
  }

  private addPositionAnnotations(chart: any, position: any, entryTime: number, candleInterval: number, exitTime: number): void {
    if (!position) return;

    const isBuy = position.action === 'BUY';
    const entryPrice = position.entry_price;
    const sl = position.stop_loss;
    const tp = position.take_profit;

    // Use rectangles to mimic position tool — reliable across all price ranges
    const rectStart = entryTime;
    const rectEnd = entryTime + candleInterval * 14;

    try {
      // Green rectangle: entry → take profit (profit zone)
      if (tp && entryPrice) {
        const topPrice = isBuy ? tp : entryPrice;
        const bottomPrice = isBuy ? entryPrice : tp;
        const s = chart.createMultipointShape([
          { time: rectStart, price: bottomPrice },
          { time: rectEnd, price: topPrice }
        ], {
          shape: 'rectangle',
          lock: true,
          disableSelection: true,
          disableSave: true,
          zOrder: 'bottom',
          overrides: {
            backgroundColor: 'rgba(34, 197, 94, 0.35)',
            borderColor: '#22c55e',
            borderWidth: 1,
            transparency: 65,
          },
        });
        if (s) this.createdShapes.push(s);
      }

      // Red rectangle: entry → stop loss (risk zone)
      if (sl && entryPrice) {
        const topPrice = isBuy ? entryPrice : sl;
        const bottomPrice = isBuy ? sl : entryPrice;
        const s = chart.createMultipointShape([
          { time: rectStart, price: bottomPrice },
          { time: rectEnd, price: topPrice }
        ], {
          shape: 'rectangle',
          lock: true,
          disableSelection: true,
          disableSave: true,
          zOrder: 'bottom',
          overrides: {
            backgroundColor: 'rgba(239, 68, 68, 0.35)',
            borderColor: '#ef4444',
            borderWidth: 1,
            transparency: 65,
          },
        });
        if (s) this.createdShapes.push(s);
      }

      // Dashed entry line (horizontal)
      if (entryPrice) {
        const s = chart.createMultipointShape([
          { time: rectStart, price: entryPrice },
          { time: rectEnd, price: entryPrice }
        ], {
          shape: 'trend_line',
          lock: true,
          disableSelection: true,
          disableSave: true,
          overrides: {
            linecolor: isBuy ? '#22c55e' : '#ef4444',
            linewidth: 2,
            linestyle: 2, // dashed
          },
        });
        if (s) this.createdShapes.push(s);
      }

      // Vertical line at entry time
      const vLineEntry = chart.createMultipointShape([
        { time: entryTime, price: entryPrice }
      ], {
        shape: 'vertical_line',
        lock: true,
        disableSelection: true,
        disableSave: true,
        overrides: {
          linecolor: '#9ca3af',
          linewidth: 1,
          linestyle: 2, // dashed
          showLabel: true,
          textcolor: '#9ca3af',
          fontsize: 11,
          bold: true,
          text: 'Entry',
        },
      });
      if (vLineEntry) this.createdShapes.push(vLineEntry);

      // Vertical line at exit time
      if (exitTime && exitTime !== entryTime) {
        const vLineExit = chart.createMultipointShape([
          { time: exitTime, price: entryPrice }
        ], {
          shape: 'vertical_line',
          lock: true,
          disableSelection: true,
          disableSave: true,
          overrides: {
            linecolor: '#9ca3af',
            linewidth: 1,
            linestyle: 2, // dashed
            showLabel: true,
            textcolor: '#9ca3af',
            fontsize: 11,
            bold: true,
            text: 'Exit',
          },
        });
        if (vLineExit) this.createdShapes.push(vLineExit);
      }
    } catch (err) {
      console.warn('Failed to add position annotations:', err);
    }
  }

  private addMarkerAnnotations(chart: any, markers: any[], lastTime: number): void {
    markers.forEach((marker: any) => {
      try {
        const rawText = (marker.text || marker.label || '').toUpperCase();

        // Skip ENTRY, FILL, EXIT markers — position tool already shows these
        if (rawText.includes('ENTRY') || rawText.includes('FILL') || rawText.includes('EXIT')) {
          return;
        }

        const rawTime = marker.timestamp || marker.time;
        const time = rawTime
          ? (typeof rawTime === 'number' ? rawTime : new Date(rawTime).getTime() / 1000)
          : lastTime;
        const price = marker.price || 0;
        const direction = marker.direction || 'buy';
        const color = marker.color || (direction === 'buy' ? '#22c55e' : '#ef4444');
        const text = marker.text || marker.label || '';

        const exec = chart.createExecutionShape()
          .setTime(time)
          .setPrice(price)
          .setDirection(direction)
          .setText(text)
          .setArrowColor(color)
          .setTextColor(color)
          .setArrowHeight(10)
          .setFont('bold 11px Arial');
        this.createdShapes.push(exec);
      } catch (err) {
        console.warn('Failed to add marker:', err);
      }
    });
  }

  private addArrowAnnotations(chart: any, arrows: any[], lastTime: number): void {
    arrows.forEach((arrow: any) => {
      try {
        const time = arrow.time ? new Date(arrow.time).getTime() / 1000 : lastTime;
        const price = arrow.price || 0;
        const isUp = arrow.direction === 'up' || arrow.direction === 'bullish';
        const direction = isUp ? 'buy' : 'sell';
        const color = arrow.color || (isUp ? '#22c55e' : '#ef4444');
        const text = this.getLabelText(arrow.label) || (isUp ? 'BOS' : 'CHoCH');

        const exec = chart.createExecutionShape()
          .setTime(time)
          .setPrice(price)
          .setDirection(direction)
          .setText(text)
          .setArrowColor(color)
          .setTextColor(color)
          .setArrowHeight(10)
          .setFont('bold 11px Arial');
        this.createdShapes.push(exec);
      } catch (err) {
        console.warn('Failed to add arrow:', err);
      }
    });
  }

  /**
   * Builds the consolidated info panel (rendered as HTML overlay, not TradingView shapes).
   * Collects: Bias, Entry, SL, TP, R:R, Fill, Exit into infoPanelEntries.
   */
  private addTextAnnotations(chart: any, texts: any[], candles: any[], firstTime: number, lastTime: number, position?: any): void {
    const entries: { text: string; color: string; bold?: boolean }[] = [];

    // 1. Bias — from backend trend text or position action
    const trendText = texts.find((t: any) => (t.text || '').includes('Trend:'));
    if (trendText) {
      const trend = (trendText.text || '').replace(/.*Trend:\s*/i, '').trim();
      const biasColor = trend.toUpperCase().includes('BULL') ? '#22c55e' : trend.toUpperCase().includes('BEAR') ? '#ef4444' : '#94a3b8';
      entries.push({ text: `Bias: ${trend}`, color: biasColor, bold: true });
    } else if (position?.action && position.action !== 'HOLD') {
      const isBuy = position.action === 'BUY';
      entries.push({ text: `Bias: ${isBuy ? 'Bullish' : 'Bearish'}`, color: isBuy ? '#22c55e' : '#ef4444', bold: true });
    }

    // 2. Entry price
    if (position?.entry_price) {
      entries.push({ text: `Entry: $${position.entry_price.toFixed(2)}`, color: '#e2e8f0' });
    }

    // 3. SL / TP
    if (position?.stop_loss) {
      entries.push({ text: `SL: $${position.stop_loss.toFixed(2)}`, color: '#ef4444' });
    }
    if (position?.take_profit) {
      entries.push({ text: `TP: $${position.take_profit.toFixed(2)}`, color: '#22c55e' });
    }

    // 4. R:R — from backend text or position data
    const rrText = texts.find((t: any) => (t.text || '').includes('R:R'));
    if (rrText) {
      entries.push({ text: (rrText.text || '').trim(), color: '#e2e8f0' });
    } else if (position?.rr_ratio) {
      entries.push({ text: `R:R = 1:${position.rr_ratio.toFixed(2)}`, color: '#e2e8f0' });
    }

    // 5. Fill — from markers
    const markers = this.chartData.annotations?.markers || [];
    const fillMarker = markers.find((m: any) => (m.text || '').toUpperCase().includes('FILL'));
    if (fillMarker) {
      const raw = fillMarker.text || '';
      const priceMatch = raw.match(/\$[\d.]+/);
      entries.push({ text: `Fill: ${priceMatch ? priceMatch[0] : raw}`, color: '#eab308' });
    }

    // 6. Exit — from markers
    const exitMarker = markers.find((m: any) => (m.text || '').toUpperCase().includes('EXIT'));
    if (exitMarker) {
      const raw = exitMarker.text || '';
      const priceMatch = raw.match(/\$[\d.]+/);
      const reasonMatch = raw.match(/\(([^)]+)\)/);
      let exitLine = 'Exit:';
      if (priceMatch) exitLine += ` ${priceMatch[0]}`;
      if (reasonMatch) {
        let reason = reasonMatch[1].replace('Position closed by broker', 'Broker close').replace(/\s*\([^)]*\)/g, '');
        exitLine += ` (${reason.trim()})`;
      }
      entries.push({ text: exitLine, color: '#e2e8f0' });
    }

    this.infoPanelEntries = entries;
  }

  private addIndicatorStudies(chart: any): void {
    if (this.chartData.indicators?.rsi) {
      try {
        chart.createStudy('Relative Strength Index', false, false, { length: 14 });
      } catch (err) {
        console.warn('Failed to add RSI study:', err);
      }
    }
    if (this.chartData.indicators?.macd) {
      try {
        chart.createStudy('MACD', false, false, { fast_length: 12, slow_length: 26, signal_length: 9 });
      } catch (err) {
        console.warn('Failed to add MACD study:', err);
      }
    }
  }

  private timeframeToInterval(timeframe: string): string {
    const map: { [key: string]: string } = {
      '1m': '1',
      '5m': '5',
      '15m': '15',
      '30m': '30',
      '1h': '60',
      '4h': '240',
      '1d': 'D',
      'D': 'D',
    };
    return map[timeframe] || 'D';
  }
}

