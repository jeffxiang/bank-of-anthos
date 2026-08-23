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

  function fillValidForm(): void {
    component.form.patchValue({
      username: 'newuser', password: 'secret', passwordRepeat: 'secret',
      firstname: 'New', lastname: 'User', birthday: '1990-01-01'
    });
  }

  it('rejects invalid username equivalence classes', () => {
    const invalidUsernames = ['a', 'user name', 'user-name', 'sixteencharacters', 'user🐻', '仮名ユーザー'];
    for (const username of invalidUsernames) {
      component.form.controls.username.setValue(username);
      expect(component.form.controls.username.invalid)
        .withContext(username)
        .toBeTrue();
    }
    component.form.controls.username.setValue('valid_user_1');
    expect(component.form.controls.username.valid).toBeTrue();
  });

  it('rejects an incomplete form without a password mismatch silently', () => {
    component.form.patchValue({ password: 'secret', passwordRepeat: 'secret' });
    component.submit();
    expect(component.error).toBe('');
    expect(component.form.controls.firstname.touched).toBeTrue();
    expect(api.createUser).not.toHaveBeenCalled();
  });

  it('clears the mismatch error once the passwords match again', () => {
    component.form.patchValue({ password: 'one', passwordRepeat: 'two' });
    expect(component.form.controls.passwordRepeat.errors?.['mismatch']).toBeTrue();
    component.form.patchValue({ passwordRepeat: 'one' });
    expect(component.form.controls.passwordRepeat.errors).toBeNull();
  });

  it('shows the server message when account creation fails', () => {
    fillValidForm();
    api.createUser.and.returnValue(throwError(() => ({
      error: 'user already exists',
      status: 409
    })));
    component.submit();
    expect(component.error).toBe('user already exists');
    expect(component.submitting).toBeFalse();
    expect(auth.login).not.toHaveBeenCalled();
  });

  it('falls back to a generic message when the failure has no body', () => {
    fillValidForm();
    api.createUser.and.returnValue(throwError(() => ({ status: 500 })));
    component.submit();
    expect(component.error).toBe('Error: Account creation failed');
    expect(component.submitting).toBeFalse();
  });

  it('reports when the account is created but the follow-up login fails', () => {
    fillValidForm();
    api.createUser.and.returnValue(of({}));
    auth.login.and.returnValue(throwError(() => new Error('invalid login')));
    component.submit();
    expect(component.error).toBe('Account created, but login failed');
    expect(component.submitting).toBeFalse();
  });
});
