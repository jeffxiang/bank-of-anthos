import { Component } from '@angular/core';
import { AbstractControl, FormBuilder, ValidationErrors, Validators } from '@angular/forms';
import { Router } from '@angular/router';
import { ApiService } from '../api.service';
import { AuthService } from '../auth/auth.service';

function passwordMismatchValidator(group: AbstractControl): ValidationErrors | null {
  const password = group.get('password');
  const passwordRepeat = group.get('passwordRepeat');
  if (!password || !passwordRepeat) return null;

  const errors = passwordRepeat.errors;
  if (errors?.['mismatch']) {
    const { mismatch, ...remaining } = errors;
    passwordRepeat.setErrors(Object.keys(remaining).length ? remaining : null);
  }
  if (!passwordRepeat.value || password.value === passwordRepeat.value) return null;

  passwordRepeat.setErrors({ ...(passwordRepeat.errors || {}), mismatch: true });
  return { passwordMismatch: true };
}

@Component({
  selector: 'app-signup',
  templateUrl: './signup.component.html',
  styleUrls: ['./signup.component.scss']
})
export class SignupComponent {
  error = '';
  submitting = false;
  maxBirthday = new Date().toISOString().slice(0, 10);
  timezones = ['-5', '-6', '-7', '0', '1'];
  form = this.fb.group({
    username: ['', [Validators.required, Validators.pattern(/^[a-zA-Z0-9_]{2,15}$/)]],
    password: ['', Validators.required],
    passwordRepeat: ['', Validators.required],
    firstname: ['', Validators.required],
    lastname: ['', Validators.required],
    address: [{ value: '123 Nth Avenue, New York City', disabled: true }, Validators.required],
    state: [{ value: 'NY', disabled: true }, Validators.required],
    zip: [{ value: '10004', disabled: true }, Validators.required],
    ssn: [{ value: '111-22-3333', disabled: true }, Validators.required],
    birthday: ['', Validators.required],
    timezone: ['-5', Validators.required]
  }, { validators: passwordMismatchValidator });

  constructor(
    private fb: FormBuilder,
    private api: ApiService,
    private auth: AuthService,
    private router: Router
  ) {}

  get passwordMismatch(): boolean {
    return this.form.controls.password.value !== this.form.controls.passwordRepeat.value;
  }

  submit(): void {
    this.error = '';
    if (this.form.invalid || this.passwordMismatch) {
      this.form.markAllAsTouched();
      this.error = this.passwordMismatch ? 'Passwords do not match' : '';
      return;
    }
    const values = this.form.getRawValue();
    const request = {
      username: values.username!,
      password: values.password!,
      'password-repeat': values.passwordRepeat!,
      firstname: values.firstname!,
      lastname: values.lastname!,
      birthday: values.birthday!,
      timezone: values.timezone!,
      address: values.address!,
      state: values.state!,
      zip: values.zip!,
      ssn: values.ssn!
    };
    this.submitting = true;
    this.api.createUser(request).subscribe({
      next: () => this.auth.login(values.username!, values.password!).subscribe({
        next: () => this.router.navigate(['/home']),
        error: () => {
          this.error = 'Account created, but login failed';
          this.submitting = false;
        }
      }),
      error: response => {
        this.error = response?.error || 'Error: Account creation failed';
        this.submitting = false;
      }
    });
  }
}
