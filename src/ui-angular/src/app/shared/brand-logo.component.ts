import { Component, Input } from '@angular/core';

@Component({
  selector: 'app-brand-logo',
  template: `
    <span class="brand-logo" [class.brand-logo-small]="size === 'small'">
      <svg class="brand-mark" viewBox="0 0 36 28" aria-hidden="true">
        <path class="brand-stripe brand-stripe-red" d="M2 17 17 3l5 3L8 21z"></path>
        <path class="brand-stripe brand-stripe-red" d="m10 22 15-14 5 3-14 14z"></path>
        <path class="brand-stripe brand-stripe-navy" d="m19 26 12-11 4 3-12 10z"></path>
      </svg>
      <span class="brand-wordmark">BANK OF ANTHOS</span>
    </span>
  `,
  styleUrls: ['./brand-logo.component.scss']
})
export class BrandLogoComponent {
  @Input() size: 'default' | 'small' = 'default';
}
