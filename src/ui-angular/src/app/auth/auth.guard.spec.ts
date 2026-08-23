import { TestBed } from '@angular/core/testing';
import { Router } from '@angular/router';
import { RouterTestingModule } from '@angular/router/testing';
import { AuthGuard } from './auth.guard';
import { AuthService } from './auth.service';

describe('AuthGuard', () => {
  let guard: AuthGuard;
  let auth: jasmine.SpyObj<AuthService>;
  let navigate: jasmine.Spy;

  beforeEach(() => {
    auth = jasmine.createSpyObj<AuthService>('AuthService', ['isAuthenticated']);
    TestBed.configureTestingModule({
      imports: [RouterTestingModule],
      providers: [
        AuthGuard,
        { provide: AuthService, useValue: auth }
      ]
    });
    guard = TestBed.inject(AuthGuard);
    navigate = spyOn(TestBed.inject(Router), 'navigate').and.returnValue(Promise.resolve(true));
  });

  it('allows navigation for an authenticated session', () => {
    auth.isAuthenticated.and.returnValue(true);
    expect(guard.canActivate()).toBeTrue();
    expect(navigate).not.toHaveBeenCalled();
  });

  it('redirects an unauthenticated session to login', () => {
    auth.isAuthenticated.and.returnValue(false);
    expect(guard.canActivate()).toBeFalse();
    expect(navigate).toHaveBeenCalledWith(['/login']);
  });
});
