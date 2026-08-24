import { TestBed } from '@angular/core/testing';
import { HttpClientTestingModule, HttpTestingController } from '@angular/common/http/testing';
import { AuthService } from './auth.service';
import { JwtClaims } from '../models';

function encodeToken(claims: object): string {
  const payload = btoa(JSON.stringify(claims))
    .replace(/\+/g, '-')
    .replace(/\//g, '_')
    .replace(/=+$/, '');
  return `header.${payload}.signature`;
}

describe('AuthService', () => {
  const claims = { user: 'testuser', acct: '1011226111', name: 'Test User', iat: 1, exp: 9999999999 };
  let service: AuthService;
  let http: HttpTestingController;

  beforeEach(() => {
    sessionStorage.clear();
    TestBed.configureTestingModule({
      imports: [HttpClientTestingModule],
      providers: [AuthService]
    });
    service = TestBed.inject(AuthService);
    http = TestBed.inject(HttpTestingController);
  });

  afterEach(() => {
    http.verify();
    sessionStorage.clear();
  });

  it('stores the token and returns the decoded claims on login', () => {
    const decoded: JwtClaims[] = [];
    service.login('testuser', 'bankofanthos').subscribe(value => decoded.push(value));
    const request = http.expectOne(
      req => req.url === '/api/userservice/login'
    );
    expect(request.request.params.get('username')).toBe('testuser');
    expect(request.request.params.get('password')).toBe('bankofanthos');
    request.flush({ token: encodeToken(claims) });
    expect(decoded).toEqual([claims]);
    expect(service.token).toBe(encodeToken(claims));
  });

  it('does not store a token when login is rejected', () => {
    let status = 0;
    service.login('testuser', 'wrong').subscribe({
      error: response => status = response.status
    });
    http.expectOne(req => req.url === '/api/userservice/login')
      .flush('unauthorized', { status: 401, statusText: 'Unauthorized' });
    expect(status).toBe(401);
    expect(service.token).toBeNull();
  });

  it('rejects a token without a payload segment', () => {
    expect(() => service.decode('not-a-jwt')).toThrowError('Invalid JWT');
  });

  it('returns null claims when no token is stored', () => {
    expect(service.claims).toBeNull();
  });

  it('returns null claims when the stored token cannot be decoded', () => {
    sessionStorage.setItem('token', 'header.@@@not-base64@@@.signature');
    expect(service.claims).toBeNull();
  });

  it('treats a missing token as unauthenticated', () => {
    expect(service.isAuthenticated()).toBeFalse();
  });

  it('clears an expired token and reports unauthenticated', () => {
    sessionStorage.setItem('token', encodeToken({ ...claims, exp: 1 }));
    expect(service.isAuthenticated()).toBeFalse();
    expect(service.token).toBeNull();
  });

  it('clears a token without an expiry claim', () => {
    sessionStorage.setItem('token', encodeToken({ user: 'testuser', acct: '1011226111' }));
    expect(service.isAuthenticated()).toBeFalse();
    expect(service.token).toBeNull();
  });

  it('reports authenticated for an unexpired token', () => {
    sessionStorage.setItem('token', encodeToken(claims));
    expect(service.isAuthenticated()).toBeTrue();
    expect(service.claims).toEqual(claims);
  });

  it('removes the token on logout', () => {
    sessionStorage.setItem('token', encodeToken(claims));
    service.logout();
    expect(service.token).toBeNull();
  });
});
