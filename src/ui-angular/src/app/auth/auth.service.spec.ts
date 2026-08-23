import { HttpClientTestingModule, HttpTestingController } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { AuthService } from './auth.service';
import { JwtClaims } from '../models';

function makeToken(claims: Partial<JwtClaims>): string {
  const payload = btoa(JSON.stringify(claims)).replace(/=+$/, '');
  return `header.${payload}.signature`;
}

describe('AuthService', () => {
  let service: AuthService;
  let http: HttpTestingController;
  const claims = { user: 'testuser', acct: '1011226111', name: 'Test User', iat: 1, exp: 9999999999 };

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

  it('stores the token and returns decoded claims on login', () => {
    const token = makeToken(claims);
    let decoded: JwtClaims | undefined;
    service.login('testuser', 'bankofanthos').subscribe(value => decoded = value);
    const request = http.expectOne(
      req => req.url === '/api/userservice/login' &&
        req.params.get('username') === 'testuser' &&
        req.params.get('password') === 'bankofanthos'
    );
    request.flush({ token });
    expect(decoded).toEqual(jasmine.objectContaining(claims));
    expect(service.token).toBe(token);
  });

  it('surfaces the login failure and stores no token', () => {
    let failed = false;
    service.login('testuser', 'wrong-password').subscribe({
      next: () => fail('expected an error'),
      error: () => failed = true
    });
    http.expectOne(req => req.url === '/api/userservice/login').flush('invalid login', {
      status: 401,
      statusText: 'Unauthorized'
    });
    expect(failed).toBeTrue();
    expect(service.token).toBeNull();
  });

  it('removes the stored token on logout', () => {
    sessionStorage.setItem('token', makeToken(claims));
    service.logout();
    expect(service.token).toBeNull();
  });

  it('returns null claims when no token is stored', () => {
    expect(service.claims).toBeNull();
  });

  it('returns null claims for a malformed token', () => {
    sessionStorage.setItem('token', 'not-a-jwt');
    expect(service.claims).toBeNull();
  });

  it('rejects a token without a payload segment', () => {
    expect(() => service.decode('only-one-part')).toThrowError('Invalid JWT');
  });

  it('decodes base64url payloads', () => {
    const decoded = service.decode(makeToken(claims));
    expect(decoded).toEqual(jasmine.objectContaining(claims));
  });

  it('accepts an unexpired session', () => {
    sessionStorage.setItem('token', makeToken(claims));
    expect(service.isAuthenticated()).toBeTrue();
  });

  it('rejects and clears an expired session', () => {
    sessionStorage.setItem('token', makeToken({ ...claims, exp: 1 }));
    expect(service.isAuthenticated()).toBeFalse();
    expect(service.token).toBeNull();
  });

  it('rejects a session with no token', () => {
    expect(service.isAuthenticated()).toBeFalse();
  });

  it('rejects a token without an exp claim', () => {
    const { exp, ...withoutExp } = claims;
    sessionStorage.setItem('token', makeToken(withoutExp));
    expect(service.isAuthenticated()).toBeFalse();
    expect(service.token).toBeNull();
  });
});
