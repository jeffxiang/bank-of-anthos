import { Pipe, PipeTransform } from '@angular/core';

@Pipe({ name: 'currencyCents' })
export class CurrencyPipe implements PipeTransform {
  transform(cents: number | null | undefined): string {
    if (cents === null || cents === undefined) return '—';
    return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(cents / 100);
  }
}
