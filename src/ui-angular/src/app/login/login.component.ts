import { Component } from '@angular/core';
import { FormBuilder, Validators } from '@angular/forms';
import { Router } from '@angular/router';
import { AuthService } from '../auth/auth.service';
import { environment } from '../../environments/environment';

@Component({
  selector: 'app-login',
  templateUrl: './login.component.html',
  styleUrls: ['./login.component.scss']
})
export class LoginComponent {
  error = '';
  submitting = false;
  form = this.fb.group({
    username: [environment.demoUsername, Validators.required],
    password: [environment.demoPassword, Validators.required]
  });

  constructor(
    private fb: FormBuilder,
    private auth: AuthService,
    private router: Router
  ) {}

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
