import { TransactionsService } from './transactions.service';
import { Contact } from './models';

describe('TransactionsService', () => {
  const service = new TransactionsService();
  const contact: Contact = {
    label: 'Alice', account_num: '1033623433', routing_num: '883745000', is_external: false
  };
  it('builds a payment payload in cents with an idempotency UUID', () => {
    const payload = service.payment('1011226111', contact, '12.34');
    expect(payload).toEqual(jasmine.objectContaining({
      fromAccountNum: '1011226111', fromRoutingNum: '883745000',
      toAccountNum: '1033623433', toRoutingNum: '883745000', amount: 1234
    }));
    expect(payload.uuid).toMatch(/^[0-9a-f-]{36}$/);
  });
  it('builds an external deposit payload', () => {
    const payload = service.deposit('1011226111', {
      ...contact, account_num: '9099791699', routing_num: '808889588', is_external: true
    }, '5');
    expect(payload).toEqual(jasmine.objectContaining({
      fromAccountNum: '9099791699', fromRoutingNum: '808889588',
      toAccountNum: '1011226111', amount: 500
    }));
  });
  it('rejects non-positive and invalid amounts', () => {
    expect(() => service.toCents('0')).toThrow();
    expect(() => service.toCents('not-a-number')).toThrow();
  });
});
