import { TestBed } from '@angular/core/testing';
import { HttpClientTestingModule, HttpTestingController } from '@angular/common/http/testing';
import { ApiService } from './api.service';

describe('ApiService', () => {
  let service: ApiService;
  let http: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      imports: [HttpClientTestingModule],
      providers: [ApiService]
    });
    service = TestBed.inject(ApiService);
    http = TestBed.inject(HttpTestingController);
  });

  afterEach(() => http.verify());

  it('accepts the ledgerwriter plain-text success response', () => {
    let response = '';
    service.transaction({ amount: 1234 }).subscribe(value => response = value);
    const request = http.expectOne('/api/ledgerwriter/transactions');
    expect(request.request.responseType).toBe('text');
    request.flush('ok', { status: 201, statusText: 'Created' });
    expect(response).toBe('ok');
  });

  it('surfaces a ledgerwriter rejection to the subscriber', () => {
    let status = 0;
    service.transaction({ amount: 1234 }).subscribe({
      next: () => fail('expected an error'),
      error: response => status = response.status
    });
    http.expectOne('/api/ledgerwriter/transactions').flush('insufficient balance', {
      status: 400,
      statusText: 'Bad Request'
    });
    expect(status).toBe(400);
  });

  it('reads the balance for an account', () => {
    let balance = 0;
    service.balance('1011226111').subscribe(value => balance = value);
    http.expectOne('/api/balancereader/balances/1011226111').flush(1000);
    expect(balance).toBe(1000);
  });

  it('reads the transaction history for an account', () => {
    const transactions = [{
      fromAccountNum: '1011226111', fromRoutingNum: '883745000',
      toAccountNum: '1033623433', toRoutingNum: '883745000',
      amount: 250, timestamp: '2024-01-01T00:00:00Z'
    }];
    let received: unknown;
    service.transactions('1011226111').subscribe(value => received = value);
    http.expectOne('/api/transactionhistory/transactions/1011226111').flush(transactions);
    expect(received).toEqual(transactions);
  });

  it('reads and creates contacts for a user', () => {
    const contact = {
      label: 'Alice', account_num: '1033623433',
      routing_num: '883745000', is_external: false
    };
    service.contacts('testuser').subscribe();
    http.expectOne('/api/contacts/contacts/testuser').flush([contact]);

    service.addContact('testuser', contact).subscribe();
    const request = http.expectOne('/api/contacts/contacts/testuser');
    expect(request.request.method).toBe('POST');
    expect(request.request.body).toEqual(contact);
    request.flush({});
  });

  it('creates a user with a form-encoded body', () => {
    service.createUser({ username: 'newuser', password: 'secret' }).subscribe();
    const request = http.expectOne('/api/userservice/users');
    expect(request.request.method).toBe('POST');
    expect(request.request.headers.get('Content-Type')).toBe('application/x-www-form-urlencoded');
    expect(request.request.body).toBe('username=newuser&password=secret');
    request.flush({});
  });
});
