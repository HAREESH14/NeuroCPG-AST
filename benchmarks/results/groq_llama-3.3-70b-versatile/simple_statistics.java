import java.util.Scanner;

public class SimpleStatistics {
    public static void main(String[] args) {
        Scanner scanner = new Scanner(System.in);
        int n = scanner.nextInt();
        if (n > 100) n = 100;
        int[] a = new int[n];
        for (int i = 0; i < n; i++) a[i] = scanner.nextInt();
        int sum = 0, min = a[0], max = a[0];
        for (int i = 0; i < n; ++i) {
            sum += a[i];
            if (a[i] < min) min = a[i];
            if (a[i] > max) max = a[i];
        }
        System.out.print("Array: ");
        for (int i = 0; i < n; i++) System.out.print(a[i] + " ");
        System.out.println();
        System.out.printf("Sum: %d\n", sum);
        System.out.printf("Avg: %.2f\n", (double) sum / n);
        System.out.printf("Min: %d\n", min);
        System.out.printf("Max: %d\n", max);
    }
}