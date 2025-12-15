/**
 * TradingView Chart Component
 * 
 * Renders candlestick charts with annotations using TradingView Charting Library
 */

import { Component, Input, OnInit, OnDestroy, AfterViewInit, ElementRef, ViewChild } from '@angular/core';
import { CommonModule } from '@angular/common';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatIconModule } from '@angular/material/icon';

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
  @ViewChild('chartContainer') chartContainer!: ElementRef;

  private widget: any;
  loading = true;
  error: string | null = null;

  ngOnInit(): void {
    if (!this.chartData) {
      this.error = 'No chart data provided';
      this.loading = false;
    }
  }

  ngAfterViewInit(): void {
    if (this.chartData && this.chartData.candles && this.chartData.candles.length > 0) {
      console.log('Chart data received:', {
        symbol: this.chartData.meta?.symbol || this.chartData.symbol,
        timeframe: this.chartData.meta?.timeframe || this.chartData.timeframe,
        candlesCount: this.chartData.candles.length,
        firstCandle: this.chartData.candles[0],
        lastCandle: this.chartData.candles[this.chartData.candles.length - 1]
      });
      this.loadTradingViewLibrary();
    } else {
      this.error = 'Invalid or empty chart data';
      this.loading = false;
      console.error('Invalid chart data:', this.chartData);
    }
  }

  ngOnDestroy(): void {
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
      if (!symbol || symbol === 'UNKNOWN' || !this.chartData.candles || this.chartData.candles.length === 0) {
        this.error = 'Invalid chart data: missing symbol or candles';
        this.loading = false;
        console.error('Chart data validation failed:', { symbol, candlesCount: this.chartData.candles?.length });
        return;
      }

      const datafeed = this.createDatafeed();
      
      this.widget = new (window as any).TradingView.widget({
        container: this.chartContainer.nativeElement,
        datafeed: datafeed,
        symbol: symbol,
        interval: this.timeframeToInterval(timeframe),
        library_path: '/libs/charting_library-master/charting_library/',
        locale: 'en',
        disabled_features: [
          'use_localstorage_for_settings',
          'volume_force_overlay',
          'header_symbol_search',
          'symbol_search_hot_key',
          'create_volume_indicator_by_default', // Disable volume by default
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
    const candles = this.chartData.candles;
    let isFirstCall = true; // Track first call to prevent infinite loops
    
    return {
      onReady: (callback: any) => {
        setTimeout(() => callback({
          supported_resolutions: ['1', '5', '15', '30', '60', '240', 'D', 'W', 'M'],
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
          timezone: 'Etc/UTC',
          ticker: symbolName,
          exchange: '',
          minmov: 1,
          pricescale: 100,
          has_intraday: true,
          has_no_volume: false,
          has_weekly_and_monthly: false,
          supported_resolutions: ['1', '5', '15', '30', '60', '240', 'D'],
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

  private addAnnotations(): void {
    if (!this.chartData.annotations || !this.widget) {
      return;
    }

    try {
      const chart = this.widget.activeChart();
      
      // Add shapes (rectangles, triangles, etc.)
      if (this.chartData.annotations.shapes && this.chartData.annotations.shapes.length > 0) {
        this.chartData.annotations.shapes.forEach((shape: any) => {
          try {
            chart.createMultipointShape(shape.points || [], {
              shape: shape.type || 'rectangle',
              overrides: shape.style || {},
            });
          } catch (err) {
            console.warn('Failed to add shape:', err);
          }
        });
      }

      // Add markers/points using createExecutionShape
      if (this.chartData.annotations.markers && this.chartData.annotations.markers.length > 0) {
        this.chartData.annotations.markers.forEach((marker: any) => {
          try {
            const time = new Date(marker.timestamp).getTime() / 1000; // Convert to seconds
            const price = marker.price || 0;
            
            chart.createExecutionShape({
              time: time,
              price: price,
              direction: marker.direction || 'buy',
              text: marker.text || marker.label || '',
              arrowHeight: 10,
              font: 'bold 12px Arial',
            });
          } catch (err) {
            console.warn('Failed to add marker:', err);
          }
        });
      }

    } catch (error) {
      console.error('Error adding annotations:', error);
      // Don't fail the whole chart if annotations fail
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

