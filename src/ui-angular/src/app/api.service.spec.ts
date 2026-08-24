import { TestBed } from '@angular/core/testing';
import { HttpClientTestingModule, HttpTestingController } from '@angular/common/http/testing';
import { ApiService } from './api.service';
import { Contact, Transaction } from './models';

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

  it('propagates ledgerwriter rejections to the caller', () => {
    let status = 0;
    service.transaction({ amount: 1234 }).subscribe({ error: response => status = response.status });
    http.expectOne('/api/ledgerwriter/transactions')
      .flush('insufficient balance', { status: 400, statusText: 'Bad Request' });
    expect(status).toBe(400);
  });

  it('reads the balance for an account', () => {
    const balances: number[] = [];
    service.balance('1011226111').subscribe(value => balances.push(value));
    http.expectOne('/api/balancereader/balances/1011226111').flush(1000);
    expect(balances).toEqual([1000]);
  });

  it('propagates an unauthorized balance read', () => {
    let status = 0;
    service.balance('1011226111').subscribe({ error: response => status = response.status });
    http.expectOne('/api/balancereader/balances/1011226111')
      .flush('unauthorized', { status: 401, statusText: 'Unauthorized' });
    expect(status).toBe(401);
  });

  it('reads the transaction history for an account', () => {
    const history: Transaction[] = [{
      fromAccountNum: '1011226111', fromRoutingNum: '883745000',
      toAccountNum: '1033623433', toRoutingNum: '883745000',
      amount: 250, timestamp: '2024-01-01T00:00:00Z'
    }];
    let response: Transaction[] = [];
    service.transactions('1011226111').subscribe(value => response = value);
    http.expectOne('/api/transactionhistory/transactions/1011226111').flush(history);
    expect(response).toEqual(history);
  });

  it('reads and adds contacts for a user', () => {
    const contact: Contact = {
      label: 'Alice', account_num: '1033623433',
      routing_num: '883745000', is_external: false
    };
    let contacts: Contact[] = [];
    service.contacts('testuser').subscribe(value => contacts = value);
    http.expectOne('/api/contacts/contacts/testuser').flush([contact]);
    expect(contacts).toEqual([contact]);

    service.addContact('testuser', contact).subscribe();
    const request = http.expectOne('/api/contacts/contacts/testuser');
    expect(request.request.method).toBe('POST');
    expect(request.request.body).toEqual(contact);
    request.flush({});
  });

  it('form-encodes the user creation request', () => {
    service.createUser({ username: 'newuser', password: 'secret', ssn: '111-22-3333' }).subscribe();
    const request = http.expectOne('/api/userservice/users');
    expect(request.request.headers.get('Content-Type')).toBe('application/x-www-form-urlencoded');
    expect(request.request.body).toBe('username=newuser&password=secret&ssn=111-22-3333');
    request.flush({});
  });

  it('propagates a duplicate user rejection', () => {
    let status = 0;
    service.createUser({ username: 'testuser' }).subscribe({
      error: response => status = response.status
    });
    http.expectOne('/api/userservice/users')
      .flush('user already exists', { status: 409, statusText: 'Conflict' });
    expect(status).toBe(409);
  });
});
