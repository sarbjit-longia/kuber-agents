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
  symbol: string;
  timeframe: string;
  candles: Array<{
    timestamp: string;
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
      this.loadTradingViewLibrary();
    } else {
      this.error = 'Invalid or empty chart data';
      this.loading = false;
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
      const datafeed = this.createDatafeed();
      
      this.widget = new (window as any).TradingView.widget({
        container: this.chartContainer.nativeElement,
        datafeed: datafeed,
        symbol: this.chartData.symbol,
        interval: this.timeframeToInterval(this.chartData.timeframe),
        library_path: '/libs/charting_library-master/charting_library/',
        locale: 'en',
        disabled_features: [
          'use_localstorage_for_settings',
          'volume_force_overlay',
          'header_symbol_search',
          'symbol_search_hot_key',
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
        },
      });

      this.widget.onChartReady(() => {
        this.addAnnotations();
        this.loading = false;
      });

    } catch (error) {
      console.error('Error initializing chart:', error);
      this.error = 'Failed to initialize chart';
      this.loading = false;
    }
  }

  private createDatafeed(): any {
    const candles = this.chartData.candles;
    
    return {
      onReady: (callback: any) => {
        setTimeout(() => callback({
          supported_resolutions: ['1', '5', '15', '30', '60', '240', 'D', 'W', 'M'],
          supports_marks: true,
          supports_timescale_marks: true,
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
          has_weekly_and_monthly: false,
          supported_resolutions: ['1', '5', '15', '30', '60', '240', 'D'],
          volume_precision: 2,
          data_status: 'streaming',
        };
        setTimeout(() => onSymbolResolvedCallback(symbolInfo), 0);
      },

      getBars: (symbolInfo: any, resolution: string, periodParams: any, onHistoryCallback: any, onErrorCallback: any) => {
        try {
          const bars = candles.map(candle => ({
            time: new Date(candle.timestamp).getTime(),
            open: candle.open,
            high: candle.high,
            low: candle.low,
            close: candle.close,
            volume: candle.volume,
          }));

          onHistoryCallback(bars, { noData: bars.length === 0 });
        } catch (error) {
          console.error('Error getting bars:', error);
          onErrorCallback('Failed to load chart data');
        }
      },

      subscribeBars: () => {},
      unsubscribeBars: () => {},
    };
  }

  private addAnnotations(): void {
    if (!this.chartData.annotations || !this.widget) {
      return;
    }

    try {
      const chart = this.widget.activeChart();
      
      // Add shapes (rectangles, etc.)
      if (this.chartData.annotations.shapes) {
        this.chartData.annotations.shapes.forEach(shape => {
          chart.createShape(shape.points, {
            shape: shape.type || 'rectangle',
            overrides: shape.style || {},
          });
        });
      }

      // Add markers
      if (this.chartData.annotations.markers) {
        this.chartData.annotations.markers.forEach(marker => {
          chart.createMarker({
            time: new Date(marker.timestamp).getTime() / 1000,
            color: marker.color || '#2196F3',
            text: marker.text || '',
            label: marker.label || '',
            labelFontColor: '#FFFFFF',
            minSize: 14,
          });
        });
      }

    } catch (error) {
      console.error('Error adding annotations:', error);
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

