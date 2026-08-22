import { CurrencyPipe } from './currency.pipe';

describe('CurrencyPipe', () => {
  it('formats cents as dollars', () => {
    expect(new CurrencyPipe().transform(717970)).toBe('$7,179.70');
  });
  it('handles a missing value', () => {
    expect(new CurrencyPipe().transform(null)).toBe('—');
  });
});
