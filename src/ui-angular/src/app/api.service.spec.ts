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
});
