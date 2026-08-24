import { TestBed } from '@angular/core/testing';
import { HTTP_INTERCEPTORS, HttpClient } from '@angular/common/http';
import { HttpClientTestingModule, HttpTestingController } from '@angular/common/http/testing';
import { AuthInterceptor } from './auth.interceptor';
import { AuthService } from './auth.service';

describe('AuthInterceptor', () => {
  let http: HttpClient;
  let controller: HttpTestingController;
  let auth: jasmine.SpyObj<AuthService>;

  beforeEach(() => {
    auth = jasmine.createSpyObj<AuthService>('AuthService', ['isAuthenticated'], { token: 'jwt-token' });
    TestBed.configureTestingModule({
      imports: [HttpClientTestingModule],
      providers: [
        { provide: AuthService, useValue: auth },
        { provide: HTTP_INTERCEPTORS, useClass: AuthInterceptor, multi: true }
      ]
    });
    http = TestBed.inject(HttpClient);
    controller = TestBed.inject(HttpTestingController);
  });

  afterEach(() => controller.verify());

  it('attaches the bearer token to authenticated requests', () => {
    auth.isAuthenticated.and.returnValue(true);
    http.get('/api/balancereader/balances/1011226111').subscribe();
    const request = controller.expectOne('/api/balancereader/balances/1011226111');
    expect(request.request.headers.get('Authorization')).toBe('Bearer jwt-token');
    request.flush(0);
  });

  it('leaves requests unauthenticated when the session is expired', () => {
    auth.isAuthenticated.and.returnValue(false);
    http.get('/api/balancereader/balances/1011226111').subscribe();
    const request = controller.expectOne('/api/balancereader/balances/1011226111');
    expect(request.request.headers.has('Authorization')).toBeFalse();
    request.flush(0);
  });

  it('never sends a token to the login endpoint', () => {
    auth.isAuthenticated.and.returnValue(true);
    http.get('/api/userservice/login').subscribe();
    const request = controller.expectOne('/api/userservice/login');
    expect(request.request.headers.has('Authorization')).toBeFalse();
    request.flush({ token: 'jwt-token' });
  });
});
