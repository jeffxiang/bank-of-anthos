import { Component, Input } from '@angular/core';

@Component({
  selector: 'app-brand-logo',
  template: `
    <span class="brand-logo" [class.brand-logo-small]="size === 'small'">
      <span class="brand-wordmark">BANK OF ANTHOS</span>
      <svg class="brand-mark" viewBox="0 0 44 28" aria-hidden="true">
        <path class="brand-stripe brand-stripe-red" d="M1 14 29 1l6 3L7 17z"></path>
        <path class="brand-stripe brand-stripe-red" d="m5 20 28-13 6 3-28 13z"></path>
        <path class="brand-stripe brand-stripe-navy" d="m9 26 28-13 6 3-28 13z"></path>
      </svg>
    </span>
  `,
  styleUrls: ['./brand-logo.component.scss']
})
export class BrandLogoComponent {
  @Input() size: 'default' | 'small' = 'default';
}
