import { ComponentFixture, TestBed } from '@angular/core/testing';
import { ReactiveFormsModule } from '@angular/forms';
import { RouterTestingModule } from '@angular/router/testing';
import { Router } from '@angular/router';
import { of, throwError } from 'rxjs';
import { LoginComponent } from './login.component';
import { AuthService } from '../auth/auth.service';
import { RuntimeConfigService } from '../runtime-config.service';

describe('LoginComponent', () => {
  let component: LoginComponent;
  let auth: jasmine.SpyObj<AuthService>;
  const config = {
    demoUsername: 'testuser',
    demoPassword: 'bankofanthos',
    localRouting: '883745000'
  };

  beforeEach(async () => {
    auth = jasmine.createSpyObj<AuthService>('AuthService', ['login']);
    await TestBed.configureTestingModule({
      imports: [ReactiveFormsModule, RouterTestingModule],
      declarations: [LoginComponent],
      providers: [
        { provide: AuthService, useValue: auth },
        { provide: RuntimeConfigService, useValue: config }
      ]
    }).compileComponents();
    spyOn(TestBed.inject(Router), 'navigate').and.returnValue(Promise.resolve(true));
    const fixture: ComponentFixture<LoginComponent> = TestBed.createComponent(LoginComponent);
    component = fixture.componentInstance;
  });

  it('submits credentials on success', () => {
    auth.login.and.returnValue(of({ user: 'testuser', acct: '1', name: 'Test User', iat: 1, exp: 2 }));
    expect(component.form.value).toEqual({
      username: 'testuser',
      password: 'bankofanthos'
    });
    component.submit();
    expect(auth.login).toHaveBeenCalledWith('testuser', 'bankofanthos');
  });

  it('shows the equivalent login failure message', () => {
    auth.login.and.returnValue(throwError(() => new Error('invalid login')));
    component.submit();
    expect(component.error).toBe('Login Failed');
  });

  it('leaves the prefill empty when runtime config has no demo credentials', () => {
    config.demoUsername = '';
    config.demoPassword = '';
    const emptyComponent = TestBed.createComponent(LoginComponent).componentInstance;
    expect(emptyComponent.form.value).toEqual({
      username: '',
      password: ''
    });
  });
});
