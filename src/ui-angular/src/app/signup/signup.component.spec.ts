import { ComponentFixture, TestBed } from '@angular/core/testing';
import { ReactiveFormsModule } from '@angular/forms';
import { RouterTestingModule } from '@angular/router/testing';
import { Router } from '@angular/router';
import { of } from 'rxjs';
import { SignupComponent } from './signup.component';
import { ApiService } from '../api.service';
import { AuthService } from '../auth/auth.service';

describe('SignupComponent', () => {
  let component: SignupComponent;
  let api: jasmine.SpyObj<ApiService>;
  let auth: jasmine.SpyObj<AuthService>;

  beforeEach(async () => {
    api = jasmine.createSpyObj<ApiService>('ApiService', ['createUser']);
    auth = jasmine.createSpyObj<AuthService>('AuthService', ['login']);
    auth.login.and.returnValue(of({
      user: 'newuser', acct: '1', name: 'New User', iat: 1, exp: 9999999999
    }));
    await TestBed.configureTestingModule({
      imports: [ReactiveFormsModule, RouterTestingModule],
      declarations: [SignupComponent],
      providers: [
        { provide: ApiService, useValue: api },
        { provide: AuthService, useValue: auth }
      ]
    }).compileComponents();
    spyOn(TestBed.inject(Router), 'navigate').and.returnValue(Promise.resolve(true));
    const fixture: ComponentFixture<SignupComponent> = TestBed.createComponent(SignupComponent);
    component = fixture.componentInstance;
  });

  it('rejects invalid usernames and mismatched passwords', () => {
    component.form.patchValue({ username: 'x', password: 'one', passwordRepeat: 'two' });
    component.submit();
    expect(component.form.controls.username.invalid).toBeTrue();
    expect(component.error).toBe('Passwords do not match');
    expect(api.createUser).not.toHaveBeenCalled();
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
});
