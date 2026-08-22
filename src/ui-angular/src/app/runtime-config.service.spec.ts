import { HttpClientTestingModule, HttpTestingController } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { RuntimeConfigService } from './runtime-config.service';

describe('RuntimeConfigService', () => {
  let service: RuntimeConfigService;
  let http: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      imports: [HttpClientTestingModule],
      providers: [RuntimeConfigService]
    });
    service = TestBed.inject(RuntimeConfigService);
    http = TestBed.inject(HttpTestingController);
  });

  afterEach(() => http.verify());

  it('loads runtime demo credentials and routing number', async () => {
    const loading = service.load();
    http.expectOne('/config.json').flush({
      demoUsername: 'runtime-user',
      demoPassword: 'runtime-password',
      localRouting: '999999999'
    });
    await loading;
    expect(service.demoUsername).toBe('runtime-user');
    expect(service.demoPassword).toBe('runtime-password');
    expect(service.localRouting).toBe('999999999');
  });

  it('keeps empty defaults when runtime config is unavailable', async () => {
    const loading = service.load();
    http.expectOne('/config.json').flush('missing', {
      status: 404,
      statusText: 'Not Found'
    });
    await loading;
    expect(service.demoUsername).toBe('');
    expect(service.demoPassword).toBe('');
    expect(service.localRouting).toBe('');
  });
});
