import { ComponentFixture, TestBed } from '@angular/core/testing';
import { CommonModule } from '@angular/common';
import { Router } from '@angular/router';
import { RouterTestingModule } from '@angular/router/testing';
import { AppComponent } from './app.component';
import { AuthService } from './auth/auth.service';
import { BrandLogoComponent } from './shared/brand-logo.component';

describe('AppComponent', () => {
  let fixture: ComponentFixture<AppComponent>;
  let auth: { claims: { name: string } | null; logout: jasmine.Spy };
  let router: Router;

  beforeEach(async () => {
    auth = { claims: null, logout: jasmine.createSpy('logout') };
    await TestBed.configureTestingModule({
      imports: [CommonModule, RouterTestingModule],
      declarations: [AppComponent, BrandLogoComponent],
      providers: [
        { provide: AuthService, useValue: auth }
      ]
    }).compileComponents();
    fixture = TestBed.createComponent(AppComponent);
    router = TestBed.inject(Router);
  });

  it('renders the router outlet shell', () => {
    expect(fixture.componentInstance).toBeTruthy();
    expect(fixture.nativeElement.querySelector('router-outlet')).toBeTruthy();
  });

  it('hides account actions on login and signup with an active session', () => {
    auth.claims = { name: 'Test User' };
    const url = spyOnProperty(router, 'url', 'get').and.returnValue('/login');

    fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('.account-actions')).toBeNull();
    expect(fixture.nativeElement.querySelector('app-brand-logo')).toBeTruthy();

    url.and.returnValue('/signup');
    fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('.account-actions')).toBeNull();
  });

  it('shows account actions on home with an active session', () => {
    auth.claims = { name: 'Test User' };
    spyOnProperty(router, 'url', 'get').and.returnValue('/home?tab=deposits');
    expect(fixture.componentInstance.displayName).toBe('Test User');
    expect(fixture.componentInstance.showAccountActions).toBeTrue();
  });

  it('hides account actions without a session', () => {
    spyOnProperty(router, 'url', 'get').and.returnValue('/home');
    expect(fixture.componentInstance.displayName).toBe('');
    expect(fixture.componentInstance.showAccountActions).toBeFalse();
  });

  it('clears the session and returns to login on logout', () => {
    const navigate = spyOn(router, 'navigate').and.returnValue(Promise.resolve(true));
    fixture.componentInstance.logout();
    expect(auth.logout).toHaveBeenCalled();
    expect(navigate).toHaveBeenCalledWith(['/login']);
  });
});
