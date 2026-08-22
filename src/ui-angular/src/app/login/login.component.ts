import { Component } from '@angular/core';
import { FormBuilder, Validators } from '@angular/forms';
import { Router } from '@angular/router';
import { AuthService } from '../auth/auth.service';
import { RuntimeConfigService } from '../runtime-config.service';

@Component({
  selector: 'app-login',
  templateUrl: './login.component.html',
  styleUrls: ['./login.component.scss']
})
export class LoginComponent {
  error = '';
  submitting = false;
  form = this.fb.group({
    username: ['', Validators.required],
    password: ['', Validators.required]
  });

  constructor(
    private fb: FormBuilder,
    private auth: AuthService,
    private router: Router,
    private config: RuntimeConfigService
  ) {
    this.form.patchValue({
      username: this.config.demoUsername,
      password: this.config.demoPassword
    });
  }

  submit(): void {
    this.error = '';
    if (this.form.invalid) {
      this.form.markAllAsTouched();
      return;
    }
    this.submitting = true;
    this.auth.login(this.form.value.username!, this.form.value.password!).subscribe({
      next: () => this.router.navigate(['/home']),
      error: () => {
        this.error = 'Login Failed';
        this.submitting = false;
      }
    });
  }
}
