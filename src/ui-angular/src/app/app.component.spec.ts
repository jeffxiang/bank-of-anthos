import { ComponentFixture, TestBed } from '@angular/core/testing';
import { CommonModule } from '@angular/common';
import { RouterTestingModule } from '@angular/router/testing';
import { AppComponent } from './app.component';
import { AuthService } from './auth/auth.service';
import { BrandLogoComponent } from './shared/brand-logo.component';

describe('AppComponent', () => {
  let fixture: ComponentFixture<AppComponent>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [CommonModule, RouterTestingModule],
      declarations: [AppComponent, BrandLogoComponent],
      providers: [
        { provide: AuthService, useValue: { claims: null, logout: jasmine.createSpy('logout') } }
      ]
    }).compileComponents();
    fixture = TestBed.createComponent(AppComponent);
  });

  it('renders the router outlet shell', () => {
    expect(fixture.componentInstance).toBeTruthy();
    expect(fixture.nativeElement.querySelector('router-outlet')).toBeTruthy();
  });
});
