import java.util.Scanner;

public class SumAndAverage {
    public static float calculateSum(int[] arr, int n) {
        int i;
        float sum = 0;
        for (i = 0; i < n; i++) {
            sum = sum + arr[i];
        }
        return sum;
    }

    public static float calculateAverage(int[] arr, int n) {
        float sum = calculateSum(arr, n);
        return sum / n;
    }

    public static int findMax(int[] arr, int n) {
        int i;
        int maxVal = arr[0];
        for (i = 1; i < n; i++) {
            if (arr[i] > maxVal) {
                maxVal = arr[i];
            }
        }
        return maxVal;
    }

    public static int findMin(int[] arr, int n) {
        int i;
        int minVal = arr[0];
        for (i = 1; i < n; i++) {
            if (arr[i] < minVal) {
                minVal = arr[i];
            }
        }
        return minVal;
    }

    public static void main(String[] args) {
        int[] numbers = new int[100];
        Scanner scanner = new Scanner(System.in);
        int count = scanner.nextInt();
        if (count > 100) count = 100;
        for (int i = 0; i < count; i++) {
            numbers[i] = scanner.nextInt();
        }
        scanner.close();

        float sum, avg;
        int maximum, minimum;

        sum = calculateSum(numbers, count);
        avg = calculateAverage(numbers, count);
        maximum = findMax(numbers, count);
        minimum = findMin(numbers, count);

        System.out.printf("Sum: %.2f\n", sum);
        System.out.printf("Average: %.2f\n", avg);
        System.out.printf("Maximum: %d\n", maximum);
        System.out.printf("Minimum: %d\n", minimum);
    }
}