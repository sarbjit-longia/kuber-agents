import { Component, Input, OnInit, OnDestroy, ViewChild, ElementRef, AfterViewInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { MatCardModule } from '@angular/material/card';
import { MatChipsModule } from '@angular/material/chips';
import { MatIconModule } from '@angular/material/icon';
import { MatButtonModule } from '@angular/material/button';
import { MatTooltipModule } from '@angular/material/tooltip';

declare const TradingView: any;

@Component({
  selector: 'app-strategy-chart',
  standalone: true,
  imports: [
    CommonModule,
    MatCardModule,
    MatChipsModule,
    MatIconModule,
    MatButtonModule,
    MatTooltipModule
  ],
  templateUrl: './strategy-chart.component.html',
  styleUrls: ['./strategy-chart.component.scss']
})
export class StrategyChartComponent implements OnInit, AfterViewInit, OnDestroy {
  @Input() chartData: any;
  @ViewChild('chartContainer') chartContainer!: ElementRef;

  widget: any;
  expanded: boolean = false;

  ngOnInit(): void {
    // Load TradingView library if not already loaded
    this.loadTradingViewLibrary();
  }

  ngAfterViewInit(): void {
    // Initialize chart after view is ready
    if (this.chartData) {
      setTimeout(() => this.initializeChart(), 500);
    }
  }

  ngOnDestroy(): void {
    if (this.widget) {
      this.widget.remove();
    }
  }

  loadTradingViewLibrary(): void {
    // Check if TradingView is already loaded
    if (typeof TradingView !== 'undefined') {
      return;
    }

    // Load the charting library script
    const script = document.createElement('script');
    script.src = '/libs/charting_library-master/charting_library/charting_library.standalone.js';
    script.async = true;
    script.onload = () => {
      console.log('TradingView library loaded');
      if (this.chartContainer) {
        this.initializeChart();
      }
    };
    document.head.appendChild(script);
  }

  initializeChart(): void {
    if (!this.chartData || !this.chartContainer || typeof TradingView === 'undefined') {
      return;
    }

    const chartData = this.chartData;

    // Create a simple datafeed
    const datafeed = {
      onReady: (callback: any) => {
        setTimeout(() => callback({
          supported_resolutions: ['1', '5', '15', '30', '60', '240', 'D'],
          supports_marks: true,
          supports_time: true,
        }));
      },
      
      searchSymbols: (userInput: string, exchange: string, symbolType: string, onResultReadyCallback: any) => {
        onResultReadyCallback([]);
      },
      
      resolveSymbol: (symbolName: string, onSymbolResolvedCallback: any, onResolveErrorCallback: any) => {
        // Detect if symbol is forex (contains underscore like EUR_USD)
        const isForex = chartData.meta.symbol.includes('_');
        
        // For forex: 5 decimals (100000) except JPY pairs which use 3 decimals (1000)
        // For stocks/crypto: 2 decimals (100)
        let pricescale = 100; // Default: stocks (2 decimals)
        if (isForex) {
          // Check if JPY pair (3 decimals)
          if (chartData.meta.symbol.includes('JPY')) {
            pricescale = 1000; // 3 decimals for JPY pairs
          } else {
            pricescale = 100000; // 5 decimals for other forex
          }
        }
        
        const symbolInfo = {
          name: chartData.meta.symbol,
          description: chartData.meta.symbol,
          type: isForex ? 'forex' : 'stock',
          session: '24x7',
          timezone: 'Etc/UTC',
          ticker: chartData.meta.symbol,
          exchange: '',
          minmov: 1,
          pricescale: pricescale, // Dynamic based on asset type
          has_intraday: true,
          supported_resolutions: ['1', '5', '15', '30', '60', '240', 'D'],
          volume_precision: 2,
          data_status: 'streaming',
        };
        setTimeout(() => onSymbolResolvedCallback(symbolInfo), 0);
      },
      
      getBars: (symbolInfo: any, resolution: string, periodParams: any, onHistoryCallback: any, onErrorCallback: any) => {
        try {
          const bars = chartData.candles.map((candle: any) => ({
            time: new Date(candle.time).getTime(),
            open: candle.open,
            high: candle.high,
            low: candle.low,
            close: candle.close,
            volume: candle.volume
          }));
          
          onHistoryCallback(bars, { noData: bars.length === 0 });
        } catch (error) {
          console.error('getBars error:', error);
          onErrorCallback(error);
        }
      },
      
      subscribeBars: (symbolInfo: any, resolution: string, onRealtimeCallback: any, subscriberUID: string, onResetCacheNeededCallback: any) => {
        // No real-time updates for historical analysis
      },
      
      unsubscribeBars: (subscriberUID: string) => {
        // Nothing to do
      }
    };

    // Initialize TradingView widget
    this.widget = new TradingView.widget({
      container: this.chartContainer.nativeElement,
      datafeed: datafeed,
      symbol: chartData.meta.symbol,
      interval: this.mapTimeframeToInterval(chartData.meta.timeframe),
      library_path: '/libs/charting_library-master/charting_library/',
      locale: 'en',
      disabled_features: [
        'use_localstorage_for_settings',
        'volume_force_overlay',
        'header_symbol_search',
        'symbol_search_hot_key',
        'header_compare',
        'header_undo_redo',
        'header_screenshot',
        'header_saveload'
      ],
      enabled_features: [
        'study_templates',
        'side_toolbar_in_fullscreen_mode'
      ],
      charts_storage_url: undefined,
      charts_storage_api_version: '1.1',
      client_id: 'trading-platform',
      user_id: 'public_user',
      fullscreen: false,
      autosize: true,
      theme: 'dark',
      style: '1', // Candlestick chart
      toolbar_bg: '#1e1e1e',
      overrides: {
        'mainSeriesProperties.candleStyle.upColor': '#22c55e',
        'mainSeriesProperties.candleStyle.downColor': '#ef4444',
        'mainSeriesProperties.candleStyle.borderUpColor': '#22c55e',
        'mainSeriesProperties.candleStyle.borderDownColor': '#ef4444',
        'mainSeriesProperties.candleStyle.wickUpColor': '#22c55e',
        'mainSeriesProperties.candleStyle.wickDownColor': '#ef4444'
      }
    });

    // Wait for chart to be ready, then add annotations
    this.widget.onChartReady(() => {
      console.log('Chart ready, adding annotations...');
      this.addAnnotations();
    });
  }

  addAnnotations(): void {
    if (!this.widget || !this.chartData) {
      return;
    }

    try {
      const chart = this.widget.activeChart();
      const annotations = this.chartData.annotations;

      // Add zones (premium/discount areas)
      annotations.zones?.forEach((zone: any) => {
        chart.createShape(
          { time: this.chartData.candles[0].time },
          {
            shape: 'rectangle',
            overrides: {
              backgroundColor: zone.color,
              color: zone.color,
              transparency: 85,
              showLabel: true,
              text: zone.label?.text || ''
            },
            points: [
              { time: this.chartData.candles[0].time, price: zone.price1 },
              { time: this.chartData.candles[this.chartData.candles.length - 1].time, price: zone.price2 }
            ]
          }
        );
      });

      // Add FVG rectangles
      annotations.shapes?.forEach((shape: any) => {
        if (shape.type === 'rectangle') {
          chart.createShape(
            { time: shape.time1 },
            {
              shape: 'rectangle',
              overrides: {
                backgroundColor: shape.color,
                color: shape.border_color || shape.color,
                transparency: Math.round((1 - shape.opacity) * 100),
                linewidth: shape.border_width || 1,
                linestyle: shape.border_style === 'dotted' ? 1 : 0
              },
              points: [
                { time: shape.time1, price: shape.price1 },
                { time: this.chartData.candles[this.chartData.candles.length - 1].time, price: shape.price2 }
              ]
            }
          );
        }
      });

      // Add horizontal lines (liquidity, SL, TP)
      annotations.lines?.forEach((line: any) => {
        chart.createShape(
          { time: this.chartData.candles[0].time, price: line.price },
          {
            shape: 'horizontal_line',
            overrides: {
              linecolor: line.color,
              linewidth: line.width || 1,
              linestyle: line.style === 'dashed' ? 1 : 0,
              showLabel: true,
              text: line.label?.text || ''
            }
          }
        );
      });

      // Add markers (entry points)
      annotations.markers?.forEach((marker: any) => {
        chart.createShape(
          { time: marker.time, price: marker.price },
          {
            shape: marker.shape === 'circle' ? 'ellipse' : 'arrow_up',
            overrides: {
              color: marker.color,
              backgroundColor: marker.color,
              showLabel: true,
              text: marker.text || ''
            }
          }
        );
      });

      console.log('Annotations added successfully');
    } catch (error) {
      console.error('Error adding annotations:', error);
    }
  }

  mapTimeframeToInterval(timeframe: string): string {
    const mapping: Record<string, string> = {
      '1m': '1',
      '5m': '5',
      '15m': '15',
      '30m': '30',
      '1h': '60',
      '4h': '240',
      'D': 'D',
      '1d': 'D'
    };
    return mapping[timeframe] || '60';
  }

  getConditionPercentage(): number {
    if (!this.chartData?.decision) {
      return 0;
    }
    const { conditions_met, conditions_total } = this.chartData.decision;
    return conditions_total > 0 ? (conditions_met / conditions_total) * 100 : 0;
  }

  getActionColor(): string {
    const action = this.chartData?.decision?.action;
    if (action === 'BUY') return '#22c55e';
    if (action === 'SELL') return '#ef4444';
    return '#6b7280';
  }

  toggleExpand(): void {
    this.expanded = !this.expanded;
  }
}

