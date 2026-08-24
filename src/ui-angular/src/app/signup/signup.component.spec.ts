import { ComponentFixture, TestBed } from '@angular/core/testing';
import { ReactiveFormsModule } from '@angular/forms';
import { RouterTestingModule } from '@angular/router/testing';
import { Router } from '@angular/router';
import { NoopAnimationsModule } from '@angular/platform-browser/animations';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatSelectModule } from '@angular/material/select';
import { of, throwError } from 'rxjs';
import { SignupComponent } from './signup.component';
import { ApiService } from '../api.service';
import { AuthService } from '../auth/auth.service';

describe('SignupComponent', () => {
  let component: SignupComponent;
  let fixture: ComponentFixture<SignupComponent>;
  let api: jasmine.SpyObj<ApiService>;
  let auth: jasmine.SpyObj<AuthService>;

  beforeEach(async () => {
    api = jasmine.createSpyObj<ApiService>('ApiService', ['createUser']);
    auth = jasmine.createSpyObj<AuthService>('AuthService', ['login']);
    auth.login.and.returnValue(of({
      user: 'newuser', acct: '1', name: 'New User', iat: 1, exp: 9999999999
    }));
    await TestBed.configureTestingModule({
      imports: [
        ReactiveFormsModule,
        RouterTestingModule,
        NoopAnimationsModule,
        MatButtonModule,
        MatCardModule,
        MatFormFieldModule,
        MatInputModule,
        MatSelectModule
      ],
      declarations: [SignupComponent],
      providers: [
        { provide: ApiService, useValue: api },
        { provide: AuthService, useValue: auth }
      ]
    }).compileComponents();
    spyOn(TestBed.inject(Router), 'navigate').and.returnValue(Promise.resolve(true));
    fixture = TestBed.createComponent(SignupComponent);
    component = fixture.componentInstance;
  });

  it('rejects invalid usernames and mismatched passwords', () => {
    component.form.patchValue({ username: 'x', password: 'one', passwordRepeat: 'two' });
    component.submit();
    expect(component.form.controls.username.invalid).toBeTrue();
    expect(component.error).toBe('Passwords do not match');
    expect(api.createUser).not.toHaveBeenCalled();
  });

  it('renders an inline error for mismatched passwords', () => {
    component.form.patchValue({ password: 'one', passwordRepeat: 'two' });
    component.form.controls.passwordRepeat.markAsTouched();
    fixture.detectChanges();

    const errors = Array.from(fixture.nativeElement.querySelectorAll('mat-error')) as HTMLElement[];
    expect(errors.map(error => error.textContent?.trim())).toEqual(['Passwords do not match.']);
  });

  it('accepts valid signup fields', () => {
    component.form.patchValue({
      username: 'newuser', password: 'secret', passwordRepeat: 'secret',
      firstname: 'New', lastname: 'User', birthday: '1990-01-01'
    });
    api.createUser.and.returnValue(of({}));
    component.submit();
    expect(api.createUser).toHaveBeenCalledWith(jasmine.objectContaining({
      'password-repeat': 'secret'
    }));
  });

  const invalidUsernames = ['x', 'a'.repeat(16), 'user name', 'user🐻', 'user-name', ' user'];

  it('rejects usernames outside the allowed pattern', () => {
    invalidUsernames.forEach(username => {
      component.form.patchValue({ username });
      expect(component.form.controls.username.invalid).withContext(username).toBeTrue();
    });
  });

  it('requires every visible field before submitting', () => {
    component.form.patchValue({
      username: 'newuser', password: 'secret', passwordRepeat: 'secret',
      firstname: 'New', lastname: 'User', birthday: ''
    });
    component.submit();
    expect(component.form.controls.birthday.invalid).toBeTrue();
    expect(component.form.controls.birthday.touched).toBeTrue();
    expect(component.error).toBe('');
    expect(api.createUser).not.toHaveBeenCalled();
  });

  it('clears the mismatch error once the repeat password matches', () => {
    component.form.patchValue({ password: 'secret', passwordRepeat: 'other' });
    expect(component.form.controls.passwordRepeat.errors).toEqual({ mismatch: true });
    component.form.patchValue({ passwordRepeat: 'secret' });
    expect(component.form.controls.passwordRepeat.errors).toBeNull();
    expect(component.passwordMismatch).toBeFalse();
  });

  it('keeps the required error alongside a cleared mismatch', () => {
    component.form.patchValue({ password: 'secret', passwordRepeat: 'other' });
    component.form.patchValue({ passwordRepeat: '' });
    expect(component.form.controls.passwordRepeat.errors).toEqual({ required: true });
  });

  it('shows the server message when account creation is rejected', () => {
    component.form.patchValue({
      username: 'newuser', password: 'secret', passwordRepeat: 'secret',
      firstname: 'New', lastname: 'User', birthday: '1990-01-01'
    });
    api.createUser.and.returnValue(throwError(() => ({ error: 'user already exists' })));
    component.submit();
    expect(component.error).toBe('user already exists');
    expect(component.submitting).toBeFalse();
  });

  it('falls back to a generic message when the server sends no detail', () => {
    component.form.patchValue({
      username: 'newuser', password: 'secret', passwordRepeat: 'secret',
      firstname: 'New', lastname: 'User', birthday: '1990-01-01'
    });
    api.createUser.and.returnValue(throwError(() => ({ status: 500 })));
    component.submit();
    expect(component.error).toBe('Error: Account creation failed');
    expect(component.submitting).toBeFalse();
  });

  it('reports a failed login after the account is created', () => {
    component.form.patchValue({
      username: 'newuser', password: 'secret', passwordRepeat: 'secret',
      firstname: 'New', lastname: 'User', birthday: '1990-01-01'
    });
    api.createUser.and.returnValue(of({}));
    auth.login.and.returnValue(throwError(() => new Error('login failed')));
    component.submit();
    expect(component.error).toBe('Account created, but login failed');
    expect(component.submitting).toBeFalse();
  });

  it('sends the disabled PII fields with the creation request', () => {
    component.form.patchValue({
      username: 'newuser', password: 'secret', passwordRepeat: 'secret',
      firstname: 'New', lastname: 'User', birthday: '1990-01-01'
    });
    api.createUser.and.returnValue(of({}));
    component.submit();
    expect(api.createUser).toHaveBeenCalledWith(jasmine.objectContaining({
      address: '123 Nth Avenue, New York City', state: 'NY', zip: '10004', ssn: '111-22-3333'
    }));
  });
});
